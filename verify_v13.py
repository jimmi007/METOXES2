from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
stock = root / "metoxes" / "routers" / "stock.py"
debug = root / "metoxes" / "services" / "broker_history_debug_service.py"

checks = {
    stock: [
        '/stocks/enrichment-status',
        '/stocks/capital/realized',
        '/stocks/trading212/history-debug',
        'V13-trading212-nested-history-debug',
    ],
    debug: [
        'item.get("order")',
        'item.get("fill")',
        '"order_keys"',
        '"fill_keys"',
        '"side_counts"',
        'unknown_side_samples',
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
    print("V13 VERIFY OK")
    print("Trading212 nested order/fill history parser installed")
    print("GET /stocks/trading212/history-debug?limit=50")
    raise SystemExit(0)

raise SystemExit(1)
