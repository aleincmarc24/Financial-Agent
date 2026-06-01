import os, json, logging, gspread
from datetime import datetime, timedelta, timezone
from openai import OpenAI
import resend

# ─── SECRETS (da Replit Secrets) ──────────────────────────────────────────────
GOOGLE_CREDS = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
SHEET_ID = os.environ["SHEET_ID"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
TO_EMAIL = os.environ["TO_EMAIL"]

# ─── SETUP GLOBALE ────────────────────────────────────────────────────────────
gc = gspread.service_account_from_dict(GOOGLE_CREDS)
sh = gc.open_by_key(SHEET_ID)
client = OpenAI(api_key=OPENAI_API_KEY)
resend.api_key = RESEND_API_KEY

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# ─── CONFIGURAZIONE FOGLI ─────────────────────────────────────────────────────
TAB_TRANSACTIONS = "transactions"
TAB_SUMMARY = "weekly_summary"

COL_DATE = "date"
COL_AMOUNT = "amount"
COL_CATEGORY = "category"

# Ordine ESATTO delle categorie in weekly_summary (dopo 'net')
CATEGORIES = [
    "food and grocery",
    "transport",
    "housing and tax or legacy",
    "shopping",
    "entertainment",
    "health",
    "income",
    "subscription",
    "investment",
    "altro",
]

# Convenzione segni: spese negative → EXPENSE_SIGN = -1
EXPENSE_SIGN = -1


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_week_dates():
    today = datetime.now(timezone.utc).date()
    start_of_week = today - timedelta(days=today.weekday())
    curr_week = (
        f"{start_of_week.isocalendar()[0]}-W{start_of_week.isocalendar()[1]:02d}"
    )
    week_start_str = start_of_week.strftime("%Y-%m-%d")

    prev_start = start_of_week - timedelta(days=7)
    prev_week = f"{prev_start.isocalendar()[0]}-W{prev_start.isocalendar()[1]:02d}"

    return curr_week, week_start_str, prev_week


def _parse_float(val) -> float:
    if val is None or val == "" or str(val).lower() in ["n/a", "na", "-"]:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = str(val).replace(",", "").replace("€", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_date(val):
    if not val:
        return None
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def calc_pct(curr, prev):
    if prev == 0:
        return "+100%" if curr > 0 else "N/A"
    return f"{((curr - prev) / abs(prev)) * 100:+.1f}%"


# ─── LOGICA CORE ──────────────────────────────────────────────────────────────
def aggregate_transactions(curr_week_str):
    ws = sh.worksheet(TAB_TRANSACTIONS)
    records = ws.get_all_records()

    agg = {"spend": 0.0, "income": 0.0, "categories": {c: 0.0 for c in CATEGORIES}}

    target_year, target_week_num = map(int, curr_week_str.split("-W"))

    for r in records:
        d = parse_date(r.get(COL_DATE))
        if not d:
            continue

        iso_y, iso_w, _ = d.isocalendar()
        if iso_y != target_year or iso_w != target_week_num:
            continue

        amt = _parse_float(r.get(COL_AMOUNT, 0))
        cat_raw = r.get(COL_CATEGORY, "").strip().lower()
        cat = cat_raw if cat_raw in CATEGORIES else "altro"

        if amt * EXPENSE_SIGN > 0:  # Spesa: -10 * -1 = 10 > 0 → True
            agg["spend"] += amt
            agg["categories"][cat] += amt
        else:  # Entrata
            agg["income"] += amt
            agg["categories"][cat] += amt

    agg["net"] = agg["income"] + agg["spend"]
    return agg


def fetch_previous_summary(prev_week_str):
    ws = sh.worksheet(TAB_SUMMARY)
    headers = ws.row_values(1)

    try:
        col_idx_week = headers.index("week")
    except ValueError:
        col_idx_week = 0

    rows = ws.get_all_values()[1:]

    for r in reversed(rows):
        if len(r) > col_idx_week and r[col_idx_week] == prev_week_str:
            prev_data = {
                "spend": _parse_float(r[2] if len(r) > 2 else 0),
                "income": _parse_float(r[4] if len(r) > 4 else 0),
                "categories": {},
            }
            for i, cat in enumerate(CATEGORIES):
                val_idx = 7 + (i * 2)
                prev_data["categories"][cat] = _parse_float(
                    r[val_idx] if len(r) > val_idx else 0
                )
            return prev_data

    return None


def write_summary_row(curr_week, week_start, agg, prev):
    ws = sh.worksheet(TAB_SUMMARY)

    row = [curr_week, week_start, round(agg["spend"], 2)]
    row.append(calc_pct(agg["spend"], prev["spend"] if prev else 0))
    row.append(round(agg["income"], 2))
    row.append(calc_pct(agg["income"], prev["income"] if prev else 0))
    row.append(round(agg["net"], 2))

    for cat in CATEGORIES:
        curr_val = agg["categories"].get(cat, 0)
        prev_val = prev["categories"].get(cat, 0) if prev else 0
        row.append(round(curr_val, 2))
        row.append(calc_pct(curr_val, prev_val))

    ws.append_row(row)
    logging.info(f"✅ Riga scritta per {curr_week}")


def generate_and_send_email(curr_week, agg, prev):
    payload = {
        "week": curr_week,
        "total_spend": round(agg["spend"], 2),
        "spend_pct": calc_pct(agg["spend"], prev["spend"] if prev else 0),
        "total_income": round(agg["income"], 2),
        "income_pct": calc_pct(agg["income"], prev["income"] if prev else 0),
        "categories": {
            c: {
                "val": round(agg["categories"].get(c, 0), 2),
                "pct": calc_pct(
                    agg["categories"].get(c, 0),
                    prev["categories"].get(c, 0) if prev else 0,
                ),
            }
            for c in CATEGORIES
        },
    }

    prompt = f"""Sei un assistente finanziario. Genera un report settimanale in ITALIANO.
Struttura HTML obbligatoria:
1. Totale Spesa e Totale Entrata della settimana con variazione % vs prec.
2. Elenco o tabella dettagliata per ogni categoria (Importo $ e Variazione %).
3. 1 breve insight concreto.
REGOLE: Usa SOLO i numeri forniti. Non inventare. Restituisci SOLO HTML valido, niente markdown, niente saluti.
Dati: {json.dumps(payload, ensure_ascii=False)}"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=600,
    )
    html = res.choices[0].message.content.strip()

    resend.Emails.send(
        {
            "from": os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev"),
            "to": [TO_EMAIL],
            "subject": f"📊 Report Spese {curr_week}",
            "html": html,
        }
    )
    logging.info("📧 Email inviata con successo")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
def main():
    logging.info("🔄 Avvio generazione report settimanale")

    curr_week, week_start, prev_week = get_week_dates()
    logging.info(f"📅 Settimana corrente: {curr_week} | Inizia il: {week_start}")

    ws_trans = sh.worksheet(TAB_TRANSACTIONS)
    sample = ws_trans.get_all_records()[:3]
    logging.info(f"🔍 Campione transazioni: {sample}")

    agg = aggregate_transactions(curr_week)
    logging.info(f"💰 Totale Spese: {agg['spend']:.2f} | Entrate: {agg['income']:.2f}")

    prev = fetch_previous_summary(prev_week)

    write_summary_row(curr_week, week_start, agg, prev)

    generate_and_send_email(curr_week, agg, prev)

    logging.info("✅ Processo completato.")


if __name__ == "__main__":
    main()
