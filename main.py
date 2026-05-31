#Ruolo nel progetto: Direttore d'orchestra. Non fa lavoro pesante. Decide l'ordine, gestisce il flusso, ferma tutto se un passo critico fallisce, prepara il sistema per l'esecuzione schedulata.
#Perché isolato: Separa il controllo di flusso dalla logica specifica. Permette di aggiungere step futuri (alert, report, cleanup) senza sporcare i moduli core.
import sys
import logging
from datetime import datetime, timedelta, timezone

from config import config
from metrics import setup_logging, log_start, log_error
from fetcher import fetch_transactions
from categorizer import categorize_batch
from storage import write_to_sheets

STATE_FILE = "last_sync.txt"

def get_last_sync() -> str:
    """Legge l'ultimo timestamp di sincronizzazione. Default: 7 giorni fa."""
    try:
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

def save_last_sync(timestamp: str):
    """Salva il timestamp corrente per il prossimo run."""
    with open(STATE_FILE, "w") as f:
        f.write(timestamp)

def main():
    setup_logging(config.log_level)
    log_start()

    try:
        last_sync = get_last_sync()
        logging.info(f"STATE last_sync={last_sync}")

        # 1. Fetch Up Bank
        transactions = fetch_transactions(last_sync)
        if not transactions:
            logging.info("FETCH no_new_data. Skipping AI & Storage.")
            save_last_sync(datetime.now(timezone.utc).isoformat())
            sys.exit(0)

        # 2. Categorize AI
        categorized = categorize_batch(transactions)

        # 3. Store Sheets
        write_to_sheets(categorized)

        # Update state
        save_last_sync(datetime.now(timezone.utc).isoformat())
        logging.info("PIPELINE completed successfully.")

    except Exception as e:
        log_error("main_orchestrator", e)
        sys.exit(1)

if __name__ == "__main__":
    main()