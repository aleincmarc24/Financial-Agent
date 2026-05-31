#Ruolo nel progetto: Persiste i dati in modo leggibile e queryabile. Garantisce assenza di duplicati e scrittura efficiente.
#Perché isolato: Il backend di storage è un dettaglio implementativo. Se domani passi a SQLite, PostgreSQL o Notion, cambi solo questo file. Fetch e categorizer restano identici.
import gspread
import json
import logging
from datetime import datetime

from config import config
from metrics import log_store, log_error

SHEET_TAB = "transactions"

def _extract_sheet_id(raw: str) -> str:
    """Accetta sia l'ID puro sia l'URL completo del foglio."""
    if "/spreadsheets/d/" in raw:
        part = raw.split("/spreadsheets/d/")[1]
        return part.split("/")[0].split("?")[0]
    return raw.strip()

def _get_worksheet():
    """Inizializza client gspread e restituisce il worksheet corretto."""
    creds = json.loads(config.google_service_account_json)
    client = gspread.service_account_from_dict(creds)
    sheet_id = _extract_sheet_id(config.sheet_id)
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.worksheet(SHEET_TAB)

def write_to_sheets(categorized_txs: list[dict]):
    CATEGORY_COLORS = {
        "Food and Grocery":        (1.0, 0.84, 0.0),    # Oro
        "Transport":               (0.68, 0.85, 0.90),  # Azzurro chiaro
        "Income":                  (0.70, 0.90, 0.70),  # Verde chiaro
        "Shopping":                (1.0, 0.75, 0.50),   # Arancione chiaro
        "Subscription":            (0.80, 0.70, 0.90),  # Viola chiaro
        "Altro":                   (0.85, 0.85, 0.85),  # Grigio chiaro
        "Housing and Tax or Legacy":(0.50, 0.50, 0.50), # Grigio scuro
        "Investment":              (0.60, 0.80, 1.0),   # Blu navy chiaro
        "Health":                  (1.0, 0.75, 0.80),   # Rosa chiaro
        "Entertainment":           (1.0, 0.95, 0.60),   # Giallo chiaro
    }
    def _apply_row_colors(ws, categorized_txs: list[dict], start_row: int):
      """Colora ogni riga in base alla categoria."""
      try:
          requests = []
          sheet_id = ws._properties["sheetId"]

          for i, tx in enumerate(categorized_txs):
              cat = tx.get("category", "Altro")
              color = CATEGORY_COLORS.get(cat, (1.0, 1.0, 1.0))
              row_index = start_row + i - 1  # 0-based

              requests.append({
                  "repeatCell": {
                      "range": {
                          "sheetId": sheet_id,
                          "startRowIndex": row_index,
                          "endRowIndex": row_index + 1,
                          "startColumnIndex": 0,
                          "endColumnIndex": 8
                      },
                      "cell": {
                          "userEnteredFormat": {
                              "backgroundColor": {
                                  "red": color[0],
                                  "green": color[1],
                                  "blue": color[2]
                              }
                          }
                      },
                      "fields": "userEnteredFormat.backgroundColor"
                  }
              })

          if requests:
              ws.spreadsheet.batch_update({"requests": requests})
              logging.info(f"COLORS_APPLIED: {len(requests)} rows colored")

      except Exception as e:
          log_error("color_rows", e)

  
    """Deduplica, formatta e scrive in batch sul tab 'transazioni'."""
    if not categorized_txs:
        logging.info("STORAGE: empty_input. Skip.")
        return

    try:
        ws = _get_worksheet()

        # 1. Leggi ID esistenti per deduplica (Colonna A)
        existing_ids = set()
        try:
            col_a = ws.col_values(1)
            # Ignora header se presente
            if col_a and col_a[0].strip().lower() == "id":
                existing_ids = set(col_a[1:])
            else:
                existing_ids = set(col_a)
        except Exception:
            existing_ids = set()

        # 2. Filtra e formatta righe
        rows = []
        for tx in categorized_txs:
            tx_id = str(tx["id"])
            if tx_id in existing_ids:
                continue

            # Data: ISO → YYYY-MM-DD
            raw_date = tx.get("created_at", "")
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                formatted_date = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                formatted_date = raw_date

            rows.append([
                tx_id,
                formatted_date,
                tx.get("merchant", ""),
                float(tx.get("amount", 0)),
                tx.get("description", ""),
                tx.get("category", "Altro"),
                tx.get("subcategory", ""),
                round(float(tx.get("confidence", 0.0)), 2)
            ])

        if not rows:
            logging.info("STORAGE: all_duplicates. Skip.")
            return

        # 3. Batch write (1 chiamata API, zero duplicati)
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        # Colora le righe appena scritte
        existing_row_count = len(ws.col_values(1))
        start_row = existing_row_count - len(rows) + 1
        _apply_row_colors(ws, [tx for tx in categorized_txs if str(tx["id"]) not in existing_ids], start_row)

        log_store(len(rows))
        logging.info(f"STORAGE_OK: {len(rows)} righe scritte in '{SHEET_TAB}'")

    except Exception as e:
        log_error("storage", e)
        logging.error(f"STORAGE_FAIL: {e}")