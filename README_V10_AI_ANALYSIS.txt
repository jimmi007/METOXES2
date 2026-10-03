METOXES2 V10 — AI ANALYSIS / NEWS / FINANCIAL SERVICES / ANOMALIES / SECOND SOURCE
====================================================================================

Τι προστέθηκε
-------------
1) AI commentary ανά μετοχή
   - metoxes/services/ai_commentary_service.py
   - Εξηγεί το Final Score, 2 βασικά θετικά/κινδύνους, news/earnings,
     anomalies και το independent fundamentals cross-check.
   - Αν υπάρχει OPENAI_API_KEY χρησιμοποιεί OpenAI Responses API.
   - Χωρίς key δεν σπάει το update: χρησιμοποιεί deterministic rules fallback.

2) News + earnings context
   - metoxes/services/market_context_service.py
   - Default: Yahoo/yfinance news + earnings calendar.
   - Προαιρετικά FMP news/earnings με FMP_NEWS_ENABLED=1.
   - Cache 6 ωρών για να περιορίζονται API calls / rate limits.

3) Ξεχωριστό μοντέλο Financial Services / banks
   - metoxes/services/financial_sector_scoring_service.py
   - Δεν χρησιμοποιεί FCF/ROIC ως βασικό scoring framework.
   - Metrics: ROE 30%, Price-to-Book 20%, Profit Margin 15%,
     Revenue Growth 15%, Forward EPS Growth 20%.
   - Το Final Score εξακολουθεί να είναι το μόνο score που εμφανίζεται
     στο Excel/dashboard.
   - Financial Services επιτρέπονται ξανά στο candidate research.

4) Anomaly detection
   - metoxes/services/anomaly_detection_service.py
   - Εντοπίζει sign mismatch total return / avg monthly,
     ακραίες αποδόσεις/FCF/ROIC, μη θετικές τιμές, future purchase dates,
     score εκτός 0-100 και μεγάλες αποκλίσεις μεταξύ data providers.
   - Τα anomalies μπαίνουν στο quality payload και στο AI commentary.

5) Δεύτερη ανεξάρτητη πηγή fundamentals
   - metoxes/services/secondary_fundamentals_service.py
   - Αν υπάρχει FMP_API_KEY: FMP Key Metrics TTM για US + Europe.
   - Χωρίς FMP key: SEC EDGAR companyfacts fallback για US issuers.
   - Η δεύτερη πηγή είναι cross-check / validation. Δεν αντικαθιστά
     σιωπηρά τα primary Yahoo fundamentals.
   - Cache 12 ωρών.

Dashboard
---------
- Νέα ενότητα: AI Commentary Υφιστάμενων Μετοχών.
- Η ενότητα υποψηφίων έγινε AI Ανάλυση Υποψήφιων Μετοχών.
- Εμφανίζει μόνο Final Score — όχι relative/absolute score columns.
- Quality Alerts περιλαμβάνει και anomaly flags.

Candidate research
------------------
- ΗΠΑ + Ευρώπη παραμένουν.
- >=25% κάτω από 52-week high παραμένει.
- Financial Services ΔΕΝ εξαιρούνται πλέον: χρησιμοποιούν το ειδικό model.
- Οι τελικές 20 περνούν independent fundamentals cross-check,
  anomaly detection, news/earnings και AI commentary.

Νέο status endpoint
-------------------
GET /stocks/enrichment-status

Δείχνει αν είναι ρυθμισμένα OpenAI/FMP χωρίς να επιστρέφει τα API keys.

.env — προτεινόμενες γραμμές
----------------------------
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-6-luna

# Προαιρετικό αλλά απαιτείται για independent FMP coverage στην Ευρώπη.
FMP_API_KEY=...

# Default 0 για οικονομία API calls. Με 1 χρησιμοποιεί FMP και για news/earnings.
FMP_NEWS_ENABLED=0

# Η SEC ζητά descriptive User-Agent. Βάλε δικό σου email/identifier.
SEC_USER_AGENT=METOXES2 personal analytics your-email@example.com

Σειρά χρήσης
------------
1. Αντικατάσταση των αρχείων του ZIP στο project.
2. Restart FastAPI.
3. GET /stocks/enrichment-status
4. POST /stocks/update-excel
5. POST /stocks/research-candidates
6. Άνοιξε portfolio_dashboard.html

Σημαντικό
---------
- News/earnings, anomalies και second-source differences ΔΕΝ αλλάζουν
  αυτόματα το score. Τροφοδοτούν το commentary/quality layer.
- Το Financial Services model ΑΛΛΑΖΕΙ το Final Score των σχετικών εταιρειών,
  επειδή αντικαθιστά το ακατάλληλο generic FCF/ROIC scoring γι' αυτόν τον κλάδο.
- Για ευρωπαϊκές εταιρείες, πραγματικά ανεξάρτητο fundamentals cross-check
  χρειάζεται FMP_API_KEY. Χωρίς FMP, το SEC fallback καλύπτει μόνο US issuers.
