#Costruisce un prompt JSON vincolante chiamando un Modello LLM tramite API, e ottiene dettagli e calcola costo.
#Il cui scopo prende dati grezzi e li trasforma in dati strutturali trasformandoli in categorie e fissando concetti
import httpx
import json
import logging
from pydantic import BaseModel, ValidationError
from config import config
from metrics import log_metric, log_error

class CategorizationResult(BaseModel):
    id: str
    category: str
    confidence: float

# Solo vincolo di output: queste sono le UNICHE categorie accettabili
ALLOWED_CATEGORIES = [
    "Food and Grocery", "Transport", "Housing and Tax or Legacy", "Shopping",
    "Entertainment", "Health", "Income", "Subscription", "Investment", "Altro"
]

# Costruisci il prompt in modo sicuro (no f-string con triple quotes)
_CATEGORIES_STR = ", ".join(ALLOWED_CATEGORIES)

SYSTEM_PROMPT = """You are an intelligent financial categorization engine.

## TASK
For each transaction, analyze the merchant name, description, amount, and context.
Map it to the SINGLE most appropriate category from this EXCLUSIVE list:
{categories}

## RULES
- Return ONLY valid JSON array: [{{"id": str, "category": str, "confidence": float}}]
- `category` must match EXACTLY one item from the allowed list (case-sensitive)
- `confidence`: 0.0-1.0 based on how certain you are
- If truly ambiguous, use "Altro" with confidence < 0.6
- Use your world knowledge: you know Aldi is a supermarket, Uber can be transport or food delivery, Netflix is a subscription, etc.

## EXAMPLES
{{"merchant": "Aldi", "description": "Card purchase", "amount": -14.42}} -> "Food and Grocery"
{{"merchant": "Uber", "description": "Trip to airport", "amount": -45.00}} -> "Transport"
{{"merchant": "Netflix", "description": "Monthly subscription", "amount": -19.99}} -> "Subscription"
{{"merchant": "Replit", "description": "Pro plan", "amount": -20.00}} -> "Investment"
{{"merchant": "Unknown", "description": "POS transaction", "amount": -5.00}} -> "Altro"
""".format(categories=_CATEGORIES_STR)

def categorize_batch(transactions: list[dict], batch_size: int = 25) -> list[dict]:
    if not transactions:
        return []

    results = []
    total_cost = 0.0

    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i+batch_size]
        try:
            # Input pulito: solo i campi che servono per il ragionamento
            tx_input = [
                {
                    "id": t["id"],
                    "amount": t["amount"],
                    "description": t.get("description", ""),
                    "merchant": t.get("merchant", "")
                } for t in batch
            ]

            headers = {
                "Authorization": f"Bearer {config.llm_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": config.llm_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(tx_input, ensure_ascii=False)}
                ],
                "temperature": 0.1
            }

            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()

            # Cost tracking
            tokens = data.get("usage", {}).get("total_tokens", 0)
            cost = (tokens * 0.15) / 1_000_000
            total_cost += cost

            # Parsing + validazione
            content = data["choices"][0]["message"]["content"].strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            parsed = json.loads(content)

            # Gestisci sia lista diretta che dict con chiave
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                # Search for a list value (handles any wrapper key)
                items = next((v for v in parsed.values() if isinstance(v, list)), [parsed])
            else:
                items = [parsed]

            for item in items:
                try:
                    cat = item.get("category", "Altro")
                    # Safety fallback: se l'LLM sbaglia formato, forza categoria valida
                    if cat not in ALLOWED_CATEGORIES:
                        cat = "Altro"
                    # Merge original tx fields so storage has merchant/amount/description/created_at
                    original = next((t for t in batch if str(t["id"]) == str(item["id"])), {})
                    results.append({
                        **original,
                        "id": item["id"],
                        "category": cat,
                        "confidence": float(item.get("confidence", 0.0))
                    })
                except (KeyError, TypeError, ValueError):
                    original = next((t for t in batch if str(t.get("id")) == str(item.get("id", ""))), {})
                    results.append({**original, "id": item.get("id", "unknown"), "category": "Altro", "confidence": 0.0})

            log_metric("llm_tokens", tokens)
            log_metric("llm_cost", cost, " USD")

        except Exception as e:
            log_error("categorizer", e)
            # Fallback totale per il batch
            for t in batch:
                results.append({"id": t["id"], "category": "Altro", "confidence": 0.0})

    logging.info(f"CATEGORIZE_DONE: {len(results)} txs, cost=${total_cost:.4f}")
    return results