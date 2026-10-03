METOXES2 V12 - CAPITAL SOLD + ENRICHMENT STATUS (verified patch)
================================================================

WHY THIS VERSION
----------------
The stock.py you checked was an older file: it had Capital transactions-debug,
but it did not contain GET /stocks/capital/realized or GET /stocks/enrichment-status,
and POST /stocks/update-excel was still feeding Sold only from Freedom24.

V12 contains one consistent stock.py and the matching services.

WHAT IS INCLUDED
----------------
1. GET /stocks/enrichment-status
   - returns build = V12-capital-sold-enrichment
   - lists the endpoints expected in this build
   - reports OpenAI/FMP/SEC configuration and sold-history broker status

2. GET /stocks/capital/realized
   - calls Capital /api/v1/history/transactions?type=TRADE
   - keeps only transactionType=TRADE, note="Trade closed", status=PROCESSED
   - uses signed size as broker-history realized P/L
   - deduplicates by reference
   - converts non-EUR P/L to EUR using historical FX
   - does NOT invent commissions when Capital does not return confirmed commission rows

3. POST /stocks/update-excel
   - collects Freedom24 realized history
   - collects Capital realized history
   - merges both lookups
   - passes the merged lookup into update_portfolio_excel()
   - refreshes the compact Sold sheet on every update

4. Sold sheet
   - columns A:I only:
     symbol, sector, platform, purchase_date, purchase_price, quantity,
     current_price, percent_change, total_profit_loss
   - total_profit_loss comes ONLY from verified broker history
   - Capital P/L can be shown even when SOLD VALUE / SOLD RETURN remain pending
   - summary boxes: SOLD VALUE, SOLD RETURN, REALIZED P/L

5. Trading212
   - still intentionally pending for realized P/L
   - use GET /stocks/trading212/history-debug?limit=50 and send one BUY + one SELL

6. V10 analytics retained
   - AI commentary
   - news/earnings context
   - Financial Services model
   - anomaly detection
   - independent fundamentals cross-check

INSTALLATION - RECOMMENDED
--------------------------
A. Extract this ZIP to a temporary folder (for example Downloads\METOXES2_V12).
B. Right-click PowerShell in that extracted folder and run:

   powershell -ExecutionPolicy Bypass -File .\install_v12.ps1

The script defaults to:
C:\Users\anagn\PycharmProjects\ΜΕΤΟΧΕΣ2

It backs up the files it replaces and then verifies that the two missing routes
are really present in the installed stock.py.

If your project is elsewhere:

   powershell -ExecutionPolicy Bypass -File .\install_v12.ps1 -ProjectRoot "D:\path\to\project"

AFTER INSTALL
-------------
Restart FastAPI/Uvicorn completely. Then open /docs and run:

GET  /stocks/enrichment-status
GET  /stocks/capital/realized
POST /stocks/update-excel

Expected first response includes:
"build": "V12-capital-sold-enrichment"

For the Capital sample you supplied, the verified parser produces:
IESC = +181.30 + 179.37 = +360.67 EUR realized P/L.

IMPORTANT
---------
Do not copy only stock.py from an older ZIP. V12 stock.py depends on the V12
sold_history_service.py, broker_history_debug_service.py and excel_service.py.
Use the installer or copy the full metoxes folder contents from this ZIP.
