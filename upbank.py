import httpx
import logging
from datetime import datetime, timezone
from config import config
from metrics import log_metric, log_error

UP_BASE_URL = "https://api.up.com.au/api/v1"

def _normalize_transaction(item: dict) -> dict:
    """Trasforma risposta Up Bank → formato standard pipeline."""
    attrs = item.get("attributes", {})
    amount_obj = attrs.get("amount", {})

    # Usa valueInBaseUnits per precisione, converti a float AUD
    amount_value = amount_obj.get("valueInBaseUnits", 0) / 100  # cents → dollars

    return {
        "id": item.get("id", "up-unknown"),
        "amount": float(amount_value),
        "description": attrs.get("description", ""),
        "created_at": attrs.get("createdAt", ""),
        "settled_at": attrs.get("settledAt"),
        "status": attrs.get("status", "UNKNOWN"),
        "merchant": attrs.get("merchantName", attrs.get("description", ""))
    }

def fetch(last_sync: str) -> list[dict]:
    """Fetch transazioni da Up Bank API con paginazione e filtro temporale."""
    if not config.up_api_key:
        log_error("upbank", ValueError("UP_API_KEY missing in Secrets"))
        return []

    headers = {
        "Authorization": f"Bearer {config.up_api_key}",
        "Accept": "application/json"
    }

    all_txs = []
    next_url = f"{UP_BASE_URL}/transactions"
    params = {"filter[since]": last_sync, "page[size]": 100}
    pages = 0

    try:
        while next_url:
            resp = httpx.get(next_url, headers=headers, params=params, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()

            # Estrai e normalizza transazioni
            for item in data.get("data", []):
                # Filtra solo transazioni SETTLED (definitive)
                if item.get("attributes", {}).get("status") == "SETTLED":
                    all_txs.append(_normalize_transaction(item))

            # Paginazione JSON:API
            next_url = data.get("links", {}).get("next")
            params = {}  # Reset params dopo prima chiamata
            pages += 1

            if pages > 20:  # Safety break
                log_error("upbank", RuntimeError("Pagination limit exceeded"))
                break

        log_metric("upbank_pages", pages)
        log_metric("upbank_txs_fetched", len(all_txs))
        logging.info(f"UPBANK_FETCH: {len(all_txs)} SETTLED txs from {pages} pages")
        return all_txs

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            log_error("upbank_auth", e)
        elif e.response.status_code == 429:
            log_error("upbank_ratelimit", e)
        else:
            log_error("upbank_http", e)
        return []
    except Exception as e:
        log_error("upbank_generic", e)
        return []