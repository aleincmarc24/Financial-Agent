#Cosa contiene: Setup del logging strutturato e funzioni dedicate per tracciare costi, tempi ed errori.
#A cosa serve nel tuo progetto: Ti dice esattamente cosa ha fatto lo script, quanto ha speso in LLM, quanto tempo ha impiegato e dove si è bloccato. Senza di esso, lavori al buio: se il cron fallisce alle 3 di notte, non sai perché fino a quando non controlli manualmente.
import logging
import sys

# Configurazione strutturata (console + file)
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":"%(message)s"}',
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def setup_logging(level: str = "INFO"):
    logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))

def log_start():
    logger.info("PIPELINE_STARTED")

def log_fetch(pages: int = 1, txs_new: int = 0, duration_s: float = 0.0):
    logger.info(f"FETCH_DONE pages={pages} new_txs={txs_new} duration={duration_s:.2f}s")

def log_llm_cost(tokens: int, cost_usd: float):
    logger.info(f"LLM_COST tokens={tokens} cost_usd={cost_usd:.4f}")

def log_store(rows_written: int):
    logger.info(f"STORE_DONE rows={rows_written}")

def log_metric(name: str, value: float, unit: str = ""):
    logger.info(f"METRIC:{name}={value}{unit}")

def log_error(context: str, error: Exception):
    logger.error(f"ERROR context={context} error={error}")