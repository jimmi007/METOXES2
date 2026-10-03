from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
stock = root / "metoxes" / "routers" / "stock.py"
excel = root / "metoxes" / "services" / "excel_service.py"
sold = root / "metoxes" / "services" / "sold_history_service.py"

checks = {
    stock: [
        '/stocks/enrichment-status',
        '/stocks/capital/realized',
        'safe_collect_capital_realized_history',
        'merge_realized_history_results',
        'V12-capital-sold-enrichment',
    ],
    excel: [
        'compact_sold_sheet(',
        'sold_realized_lookup=',
        'total_profit_loss',
    ],
    sold: [
        'summarize_capital_realized_transactions',
        'transactionType',
        'Trade closed',
        'PROCESSED',
    ],
}

ok = True
for path, needles in checks.items():
    if not path.exists():
        print(f"MISSING FILE: {path}")
        ok = False
        continue
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            print(f"FAIL: {needle!r} not found in {path}")
            ok = False

if stock.exists():
    text = stock.read_text(encoding="utf-8")
    count = text.count('@router.post("/stocks/update-excel")')
    if count != 1:
        print(f"FAIL: expected one update-excel route, found {count}")
        ok = False

if ok:
    print("V12 VERIFY OK")
    print("GET  /stocks/enrichment-status")
    print("GET  /stocks/capital/realized")
    print("POST /stocks/update-excel")
    raise SystemExit(0)

raise SystemExit(1)
