METOXES2 V8 - Broker-history Sold P/L (Freedom24 first) + Sold summary boxes

What changes:

1) Sold total_profit_loss is NO LONGER estimated from current_price.
   The old formula (current_price - purchase_price) * quantity has been removed.

2) Freedom24 realized P/L is calculated from getTradesHistory:
   - type=2 sell executions only
   - broker-reported profit
   - commissions / exchange commissions
   - historical FX to EUR on the trade date
   The result is stored as net_profit_loss_eur.

3) Freedom24 history request uses max=5000 instead of the old max=100.
   The update response reports possibly_truncated=true if the broker returns
   exactly the requested maximum.

4) New endpoint:
      GET /stocks/freedom/realized
   This returns the broker-history realized summaries used by Sold.

5) Sold compact columns remain:
   symbol, sector, platform, purchase_date, purchase_price, quantity,
   current_price, percent_change, total_profit_loss

   When Freedom history is verified:
   - current_price becomes the average executed sale price in EUR
   - percent_change becomes the realized return %
   - total_profit_loss becomes the verified net realized P/L in EUR

   Trading212 / Capital rows stay BLANK in total_profit_loss until their raw
   history payloads are connected. There is deliberately no market-price fallback.

6) Sold summary boxes (same visual family as Portfolio, no VUAA box):
   - SOLD VALUE
   - SOLD RETURN
   - REALIZED P/L

   The three boxes show numeric totals only when ALL Sold rows have verified
   API history. Otherwise they show PENDING API x/y, preventing a partial total
   from being mistaken for the full realized result.

7) /stocks/update-excel now returns sold_history metadata showing Freedom24
   history status and that Trading212 / Capital are still pending raw samples.

Freedom24 sample supplied by the user:
- 50 AEGN.GR sold @ 12.12: profit -12.66, commission 3.62 EUR
- 60 AEGN.GR sold @ 12.12: profit -15.19, commission 2.90 EUR
- gross broker P/L: -27.85 EUR
- commissions: 6.52 EUR
- net realized P/L: -34.37 EUR

Next step to complete ALL brokers:
- provide one raw Trading212 historical SELL order response
- provide one raw Capital /history/transactions TRADE closed response
Then parsers can be locked to the exact account payload fields without guessing.

V12 note: use README_V12_INSTALL.txt and install_v12.ps1 for verified installation.
