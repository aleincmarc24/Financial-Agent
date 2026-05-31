#!/usr/bin/env python3
"""Diagnostico minimale: verifica ogni componente in isolamento."""

import sys
import os
import json
from pathlib import Path

print("🔍 DIAGNOSTIC START\n" + "="*50)

# 1. Check files
print("\n[1/6] Checking files...")
files = ["main.py", "config.py", "fetcher.py", "categorizer.py", "storage.py", "metrics.py", "mock_transactions.json"]
for f in files:
    exists = Path(f).exists()
    print(f"  {'✅' if exists else '❌'} {f}")
    if not exists:
        print(f"    ERROR: {f} missing. Pipeline cannot start.")
        sys.exit(1)

# 2. Check imports
print("\n[2/6] Checking imports...")
try:
    import httpx, pydantic, gspread, dotenv
    print("  ✅ All dependencies imported")
except ImportError as e:
    print(f"  ❌ Import error: {e}")
    print("  FIX: pip install -r requirements.txt")
    sys.exit(1)

# 3. Check config loading
print("\n[3/6] Checking config...")
try:
    from config import config
    print(f"  ✅ Config loaded")
    print(f"     - MOCK_MODE: {config.mock_mode}")
    print(f"     - BANK_ADAPTER: {getattr(config, 'bank_adapter', 'not set')}")
    print(f"     - LLM_API_KEY: {'[SET]' if config.llm_api_key else '[MISSING]'}")
    print(f"     - SHEET_ID: {'[SET]' if config.sheet_id else '[MISSING]'}")
    if not config.llm_api_key:
        print("  ⚠️  WARNING: LLM_API_KEY missing → AI step will fail")
    if not config.sheet_id:
        print("  ⚠️  WARNING: SHEET_ID missing → Sheets step will fail")
except Exception as e:
    print(f"  ❌ Config error: {e}")
    sys.exit(1)

# 4. Check mock file parsing
print("\n[4/6] Checking mock_transactions.json...")
try:
    with open("mock_transactions.json", "r") as f:
        raw = json.load(f)
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    print(f"  ✅ Mock file parsed: {len(data)} transactions found")
    for i, tx in enumerate(data[:3]):
        attrs = tx.get("attributes", tx) if isinstance(tx, dict) else tx
        print(f"     [{i+1}] id={attrs.get('id', 'N/A')[:20]}... amount={attrs.get('amount', {}).get('value', 'N/A')}")
except Exception as e:
    print(f"  ❌ Mock parse error: {e}")
    sys.exit(1)

# 5. Check Google Sheets auth (dry run)
print("\n[5/6] Checking Google Sheets auth (dry run)...")
try:
    creds = json.loads(config.google_service_account_json)
    client = gspread.service_account_from_dict(creds)
    # Non aprire il foglio, solo verificare che l'auth funzioni
    print(f"  ✅ Service account auth OK (email: {creds.get('client_email', 'N/A')[:30]}...)")
    print(f"  ⚠️  Next step requires sheet sharing: ensure '{creds.get('client_email')}' has Editor access")
except json.JSONDecodeError as e:
    print(f"  ❌ Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
    print("  FIX: Re-copy the entire JSON from the downloaded file, including { and }")
except Exception as e:
    print(f"  ❌ Sheets auth error: {e}")
    print("  FIX: Verify the JSON is complete and not truncated")

# 6. Summary
print("\n[6/6] Summary")
print("="*50)
print("If all ✅ above, run: python3 main.py")
print("If any ❌, fix that step first.")
print("\nExpected main.py output on success:")
print('  - "MOCK_FETCH: 3 txs caricati"')
print('  - "LLM_COST tokens=..." (check OpenAI dashboard)')
print('  - "STORE_DONE rows=3" (check Google Sheet tab "transazioni")')