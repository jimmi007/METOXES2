METOXES2 V11 - CAPITAL REALIZED P/L + SOLD REFRESH FIX
=======================================================

Τι διορθώθηκε
-------------
1. Το Sold πλέον ανανεώνεται σε ΚΑΘΕ POST /stocks/update-excel.
   Στη V10 υπήρχε compact_sold_sheet(), αλλά δεν καλούνταν από
   update_portfolio_excel(), γι' αυτό το φύλλο Sold έμενε ίδιο.

2. Capital.com realized P/L
   - GET /api/v1/history/transactions?type=TRADE
   - κρατά μόνο:
       transactionType = TRADE
       note = Trade closed
       status = PROCESSED
   - το signed size χρησιμοποιείται ως broker-history realized P/L
   - ομαδοποίηση ανά instrumentName
   - reference deduplication
   - FX conversion σε EUR όταν currency != EUR
   - ΔΕΝ αφαιρεί αυθαίρετες commissions όταν δεν υπάρχουν επιβεβαιωμένες
     commission rows.

3. Capital history completeness
   Το request χρησιμοποιεί type=TRADE ώστε να μη γεμίζει με CORPORATE_ACTION,
   DEPOSIT κ.λπ. Αν ένα διάστημα επιστρέψει >=100 TRADE rows, το V11 σπάει
   αυτόματα το date range σε μικρότερα windows για αποφυγή silent truncation.

4. Νέο endpoint
   GET /stocks/capital/realized

5. Enrichment endpoint
   GET /stocks/enrichment-status
   βρίσκεται πλέον μία φορά, καθαρά, κοντά στην αρχή του stock.py.

6. Sold summary boxes
   - SOLD VALUE
   - SOLD RETURN
   - REALIZED P/L
   Το REALIZED P/L μπορεί να εμφανιστεί από Capital broker history ακόμα κι αν
   το Capital transaction row δεν δίνει sale proceeds/cost basis.
   SOLD VALUE / SOLD RETURN μένουν PENDING VALUE API μέχρι να υπάρχουν
   επαρκή broker-backed στοιχεία για όλες τις Sold γραμμές.

7. Trading212
   Παραμένει PENDING για realized P/L μέχρι να δοθεί raw BUY/SELL sample από:
   GET /stocks/trading212/history-debug?limit=50
   Το endpoint χρησιμοποιεί το επίσημο cursor/nextPagePath history API.

Εγκατάσταση
-----------
Αντέγραψε το περιεχόμενο του ZIP πάνω από:
C:\Users\anagn\PycharmProjects\ΜΕΤΟΧΕΣ2
και κάνε restart το FastAPI/Uvicorn.

Έλεγχος
-------
GET  /stocks/enrichment-status
GET  /stocks/capital/realized
POST /stocks/update-excel

Μετά το POST /stocks/update-excel άνοιξε ξανά το portfolio.xlsx.
Το Sold θα είναι compact A:I και το Capital total_profit_loss θα προέρχεται
από το transaction history, όχι από current_price.

Trading212 επόμενο βήμα
-----------------------
GET /stocks/trading212/history-debug?limit=50
Στείλε 1 BUY και 1 SELL raw sample για να κλειδώσει το ακριβές T212 realized P/L.
