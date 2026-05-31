# Cosa contiene: Un modulo che legge .env, valida i dati, ed esporta un oggetto config unico.
#A cosa serve: Centralizza token, ID e chiavi. Evita di spargere os.getenv() in 5 file. Fa fail-fast: se manca una variabile critica, il programma si blocca all'avvio, non a metà esecuzione dopo aver sprecato chiamate API.
import os
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# Replit inietta i Secrets in os.environ automaticamente.
# load_dotenv() serve solo per test locali con file .env
load_dotenv()

class AppConfig(BaseModel):
    llm_api_key: str
    llm_model: str = "gpt-4o-mini"
    up_api_key: str = ""
    sheet_id: str
    sheet_name: str = "Transactions"
    google_service_account_json: str = "{}"
    log_level: str = "INFO"
    mock_mode: bool = True
    bank_adapter: str = "mock"  # Default: mock. Cambia in "upbank" per produzione

    @classmethod
    def from_env(cls):
        return cls(
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            up_api_key=os.getenv("UP_API_KEY", ""),
            sheet_id=os.getenv("SHEET_ID", ""),
            sheet_name=os.getenv("SHEET_NAME", "Transactions"),
            google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            mock_mode=os.getenv("MOCK_MODE", "True").lower() == "true",
            bank_adapter=os.getenv("BANK_ADAPTER", "mock")
        )

try:
    config = AppConfig.from_env()
    if not config.llm_api_key:
        raise ValueError("LLM_API_KEY mancante. Aggiungilo nei Replit Secrets.")
    if not config.sheet_id:
        raise ValueError("SHEET_ID mancante. Aggiungilo nei Replit Secrets.")
except ValidationError as e:
    print(f"❌ CONFIG VALIDATION ERROR: {e}")
    exit(1)
except Exception as e:
    print(f"❌ CONFIG ERROR: {e}")
    exit(1)