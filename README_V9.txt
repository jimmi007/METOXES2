METOXES2 V9 - Trading212 + Capital history diagnostics
======================================================

This patch builds on V8.

New endpoints:

1) GET /stocks/trading212/history-debug?limit=50
   - Calls official Trading212 historical orders endpoint.
   - Returns keys + representative BUY/SELL records.
   - Does NOT yet calculate Trading212 realized P/L until the actual response
     confirms which execution-price/fee fields your account returns.

2) GET /stocks/capital/transactions-debug
   - Calls official Capital /api/v1/history/transactions from 2020 to now.
   - Returns keys + representative "Trade closed" rows and commission rows.
   - Does NOT yet write Capital realized P/L until the sign/meaning of `size`
     and commission reference linkage are confirmed from your actual response.

Freedom24 realized P/L from V8 remains unchanged.

Why this is deliberate:
- We do not want to guess realized profit/loss fields.
- Trading212's public schema exposes order history but the execution-price
  representation must be verified from your account payload.
- Capital documents Trade closed transactions, but we will verify the sign of
  `size` and how TRADE_COMMISSION/FX_COMMISSION rows share `reference` before
  writing net P/L to Sold.

After installing:
- restart FastAPI
- call GET /stocks/trading212/history-debug?limit=50
- call GET /stocks/capital/transactions-debug
- send the two JSON responses back.

No credentials are returned by these endpoints.
