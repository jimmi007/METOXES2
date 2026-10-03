METOXES2 V14 — Collapsible Final Score Analysis
===============================================

What changed
------------
1. Existing portfolio stocks are shown as COLLAPSIBLE rows/cards in the dashboard.
   The closed row shows rank, ticker, company name, Final Score and secondary source.
   Clicking the row opens the full analysis.

2. New deterministic score explanation for every scored stock:
   - why the Final Score is high/medium/low
   - positive score drivers
   - weak points / risks
   - missing scoring metrics
   - metric-by-metric impact
   - FMP/SEC cross-check explanation
   - anomalies
   This works even when OpenAI is unavailable.

3. AI commentary now receives the score rationale as structured context.
   If OpenAI returns HTTP 429, the run stops making repeated OpenAI attempts and
   keeps the richer deterministic analysis instead of failing the portfolio update.

4. Financial Services FMP cross-check corrected:
   - normal companies: FCF Yield / ROIC validation
   - banks & Financial Services: ROE / Price-to-Book validation
   This fixes misleading bank discrepancies caused by comparing FCF/ROIC.
   Cross-check metadata does NOT directly change Final Score.

5. Candidate research also receives the richer score explanation.

Install
-------
powershell -ExecutionPolicy Bypass -File .\install_v14.ps1

Then fully restart FastAPI/Uvicorn and run:
GET  /stocks/enrichment-status
POST /stocks/update-excel

Expected build:
V14-score-accordion-fmp-explain

Open:
portfolio_dashboard.html
