#Ruolo nel progetto: Recupera le transazioni nuove da banca. È l'unico modulo che parla con la banca.
#Perché isolato: La logica di rete, paginazione e rate limit è fragile. Se CDR cambia versione o banca modifica i parametri, tocchi solo qui. Il resto della pipeline non deve conoscere i dettagli HTTP.
#Chiamata tramite API alla banca e mi aspetto di ricevere un ogetto Python Json le qui proprieta' e chavi dipendono dalla banca in questione
# PRIMA VERSIONE IMPORTA MANUALMENTE UN FILE JSON QUINDI NON FA CHIAMATA MA SIMULA LA RISPOSTA DELLA CHIAMATA
import logging
from config import config
from metrics import log_fetch, log_error

# Registry adapter: aggiungi qui nuovi adapter in futuro
BANK_ADAPTERS = {
    "upbank": "upbank",
    "mock": "mock",
    # "commbank": "commbank",  # Esempio futuro
}

def fetch_transactions(last_sync: str) -> list[dict]:
    """Dispatch alla implementazione specifica della banca configurata."""
    adapter_name = config.bank_adapter if hasattr(config, 'bank_adapter') else 'mock'

    if adapter_name not in BANK_ADAPTERS:
        log_error("fetcher", ValueError(f"Unknown bank adapter: {adapter_name}"))
        return []

    try:
        if adapter_name == "mock":
            from fetcher_mock import fetch as mock_fetch
            return mock_fetch(last_sync)
        elif adapter_name == "upbank":
            from upbank import fetch as upbank_fetch
            return upbank_fetch(last_sync)
        # elif adapter_name == "commbank":
        #     from commbank import fetch as commbank_fetch
        #     return commbank_fetch(last_sync)
        else:
            return []
    except ImportError as e:
        log_error("fetcher_import", e)
        return []
    except Exception as e:
        log_error("fetcher_dispatch", e)
        return []