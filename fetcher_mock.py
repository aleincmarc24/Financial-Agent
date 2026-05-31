import json
import logging
from pathlib import Path
from metrics import log_metric, log_error


def fetch(last_sync: str) -> list[dict]:
    """Mock adapter: legge da JSON locale in formato Up Bank JSON:API, ignora last_sync."""
    try:
        mock_file = Path("mock_transactions.json")
        if not mock_file.exists():
            raise FileNotFoundError("mock_transactions.json missing")

        with open(mock_file, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Estrai array da {"data": [...]}
        if isinstance(raw, dict):
            items = raw.get("data", [])
        else:
            items = raw

        txs = []
        for t in items:
            attrs = t.get("attributes", {})
            txs.append(
                {
                    "id": t.get("id", "mock-unknown"),
                    "amount": float(attrs.get("amount", {}).get("value", 0)),
                    "description": attrs.get("description", ""),
                    "created_at": attrs.get("createdAt", ""),
                    "merchant": attrs.get("merchantName", ""),
                    "status": attrs.get("status", "SETTLED"),
                }
            )

        log_metric("mock_txs", len(txs))
        logging.info(f"MOCK_FETCH: {len(txs)} txs caricati")
        return txs

    except Exception as e:
        log_error("mock_fetch", e)
        return []
