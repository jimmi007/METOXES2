"""Regenerate an existing dashboard snapshot without invoking brokers."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from metoxes.services.portfolio_review_service import enrich_payload
from metoxes.services.dashboard_service import HTML_TEMPLATE

if __name__ == '__main__':
    path = ROOT / 'portfolio_dashboard_data.json'
    if not path.exists():
        raise SystemExit('Run POST /stocks/update-excel first to create the dashboard data.')
    payload = json.loads(path.read_text(encoding='utf-8'))
    # Preserve the portfolio valuation date. Never relabel old quotes as current.
    payload = enrich_payload(payload, root=ROOT)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    embedded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    (ROOT/'portfolio_dashboard.html').write_text(HTML_TEMPLATE.replace('__PAYLOAD__', embedded), encoding='utf-8')
    print('Updated portfolio_dashboard.html (V26).')
    print('Candidate country, beta, Investing check and 52W data preserved.')
    print('Standalone undervalued US/Greece lists are disabled.')
