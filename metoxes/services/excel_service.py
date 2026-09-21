from pathlib import Path

from openpyxl import load_workbook, Workbook


# --------------------------------------------------
# ΑΡΧΕΙΑ
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

EXCEL_FILE = BASE_DIR / "portfolio.xlsx"
OUTPUT_FILE = BASE_DIR / "portfolio_updated.xlsx"


# Οι στήλες που θέλουμε στο τελικό Excel
HEADERS = [
    "symbol",
    "name",
    "sector",
    "country",
    "platform",
    "purchase_date",
    "purchase_price",
    "quantity",
    "current_price",
    "market_value",
    "percent_change",
    "monthly_percent_change",
    "portfolio_weight",
    "vuaa_return",
    "excess_return",
]


# --------------------------------------------------
# ΔΙΑΒΑΣΜΑ ΤΟΥ portfolio.xlsx
# --------------------------------------------------

def get_excel_stocks():

    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"Δεν βρέθηκε το Excel: {EXCEL_FILE}"
        )

    workbook = load_workbook(
        EXCEL_FILE,
        data_only=True
    )

    sheet = workbook.worksheets[0]

    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[header] = cell.column

    if "symbol" not in headers:
        workbook.close()

        raise ValueError(
            "Δεν βρέθηκε στήλη 'symbol' στο Excel"
        )

    stocks = []

    for row in range(
        2,
        sheet.max_row + 1
    ):

        symbol = sheet.cell(
            row=row,
            column=headers["symbol"]
        ).value

        if not symbol:
            continue

        stocks.append({
            "symbol": str(symbol).strip()
        })

    workbook.close()

    return stocks


# --------------------------------------------------
# LOOKUP ΤΩΝ SYMBOLS
# --------------------------------------------------

def get_symbol_lookup():

    stocks = get_excel_stocks()

    lookup = {}

    for stock in stocks:

        symbol = stock["symbol"].strip()

        # Πλήρες Yahoo ticker
        # π.χ. RHM.DE -> RHM.DE
        lookup[symbol.upper()] = symbol

        # Αφαιρούμε το suffix του χρηματιστηρίου
        # π.χ. RHM.DE -> RHM
        #      ITX.MC -> ITX
        #      LDO.MI -> LDO
        base_symbol = symbol.split(".")[0]

        # Δημιουργούμε και δεύτερη αντιστοίχιση
        # π.χ. RHM -> RHM.DE
        if base_symbol.upper() not in lookup:
            lookup[base_symbol.upper()] = symbol

    return lookup

# --------------------------------------------------
# ΔΗΜΙΟΥΡΓΙΑ ΝΕΟΥ EXCEL
# --------------------------------------------------

def create_portfolio_excel(stocks):

    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Portfolio"

    sheet.append(HEADERS)

    for stock in stocks:

        sheet.append([
            stock.get("symbol"),
            stock.get("name"),
            stock.get("sector"),
            stock.get("country"),
            stock.get("platform"),
            stock.get("purchase_date"),
            stock.get("purchase_price"),
            stock.get("quantity"),
            stock.get("current_price"),
            stock.get("market_value"),
            stock.get("percent_change"),
            stock.get("monthly_percent_change"),
            stock.get("portfolio_weight"),
            stock.get("vuaa_return"),
            stock.get("excess_return"),
        ])

    workbook.save(OUTPUT_FILE)
    workbook.close()

    return OUTPUT_FILE


# --------------------------------------------------
# ΕΝΗΜΕΡΩΣΗ ΥΠΑΡΧΟΝΤΟΣ portfolio.xlsx
# --------------------------------------------------

def update_portfolio_excel(stocks):

    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"Δεν βρέθηκε το Excel: {EXCEL_FILE}"
        )

    workbook = load_workbook(EXCEL_FILE)

    sheet = workbook.worksheets[0]

    # ----------------------------------------------
    # Βρίσκουμε τις στήλες από τις κεφαλίδες
    # ----------------------------------------------

    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[header] = cell.column

    # ----------------------------------------------
    # Προσθέτουμε στήλες που τυχόν λείπουν
    # ----------------------------------------------

    for header in HEADERS:

        if header not in headers:

            new_column = sheet.max_column + 1

            sheet.cell(
                row=1,
                column=new_column
            ).value = header

            headers[header] = new_column

    # ----------------------------------------------
    # Βρίσκουμε ποιο symbol υπάρχει σε ποια γραμμή
    # ----------------------------------------------

    symbol_rows = {}

    symbol_column = headers["symbol"]

    for row in range(
        2,
        sheet.max_row + 1
    ):

        symbol = sheet.cell(
            row=row,
            column=symbol_column
        ).value

        if symbol:

            symbol_rows[
                str(symbol).strip().upper()
            ] = row

    # ----------------------------------------------
    # UPDATE ή INSERT κάθε μετοχής
    # ----------------------------------------------

    for stock in stocks:

        symbol = stock.get("symbol")

        if not symbol:
            continue

        symbol_key = str(
            symbol
        ).strip().upper()

        # Αν υπάρχει ήδη → ενημερώνουμε τη γραμμή
        if symbol_key in symbol_rows:

            row = symbol_rows[symbol_key]

        # Αν δεν υπάρχει → δημιουργούμε νέα γραμμή
        else:

            row = sheet.max_row + 1

            sheet.cell(
                row=row,
                column=headers["symbol"]
            ).value = symbol

            symbol_rows[symbol_key] = row

        # ------------------------------------------
        # Ενημέρωση δεδομένων
        # ------------------------------------------

        fields_to_update = [
            "name",
            "platform",
            "purchase_date",
            "purchase_price",
            "quantity",
            "current_price",
            "market_value",
            "percent_change",
            "monthly_percent_change",
            "portfolio_weight",
            "vuaa_return",
            "excess_return",
        ]

        for field in fields_to_update:

            value = stock.get(field)

            # Αν δεν πήραμε τιμή, δεν σβήνουμε
            # υπάρχον περιεχόμενο του Excel
            if value is not None:

                sheet.cell(
                    row=row,
                    column=headers[field]
                ).value = value

        # sector/country:
        # ενημερώνονται μόνο αν υπάρχουν στα νέα δεδομένα.
        # Διαφορετικά κρατάμε ό,τι έχει ήδη το Excel.

        for field in [
            "sector",
            "country"
        ]:

            value = stock.get(field)

            if value is not None:

                sheet.cell(
                    row=row,
                    column=headers[field]
                ).value = value

    # ----------------------------------------------
    # ΑΠΟΘΗΚΕΥΣΗ
    # ----------------------------------------------

    workbook.save(EXCEL_FILE)
    workbook.close()

    return EXCEL_FILE