METOXES2 V13 - TRADING212 NESTED HISTORY DEBUG FIX
==================================================

What was wrong
--------------
The live Trading212 /api/v0/equity/history/orders response contains records
shaped like:

    {"order": {...}, "fill": {...}}

V12 looked for side/status/ticker at the top level. Therefore it showed:

    status_counts = {"UNKNOWN": ...}
    buy_samples = []
    sell_samples = []

What V13 changes
----------------
1. Reads side/status/ticker from item["order"].
2. Reads execution details from item["fill"].
3. Returns separate diagnostics:
       top_level_keys
       order_keys
       fill_keys
       status_counts
       side_counts
       ticker_samples
       buy_samples
       sell_samples
       unknown_side_samples
4. Keeps backward compatibility with flat historical-order payloads.
5. If explicit side is missing, it can infer BUY/SELL from signed quantity only
   as a diagnostic fallback.
6. Does NOT yet calculate Trading212 realized P/L. We first need one real BUY
   and one real SELL sample after this parser fix so execution price/value/fee
   fields can be locked safely.

Install
-------
Extract the ZIP, then from that extracted folder run:

powershell -ExecutionPolicy Bypass -File .\install_v13.ps1

Default project path:
C:\Users\anagn\PycharmProjects\ΜΕΤΟΧΕΣ2

Then fully restart FastAPI/Uvicorn.

Verify
------
GET /stocks/enrichment-status

Expected build:
V13-trading212-nested-history-debug

Then run WITHOUT a ticker filter first:
GET /stocks/trading212/history-debug?limit=50

The response should now contain order_keys/fill_keys and BUY/SELL samples when
those sides are present on the returned page.
