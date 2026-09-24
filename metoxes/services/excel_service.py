from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter


# ==========================================================
# ΑΡΧΕΙΑ
# ==========================================================

# Κεντρικός φάκελος του project ΜΕΤΟΧΕΣ2
BASE_DIR = Path(__file__).resolve().parents[2]

# Κεντρικό Excel
EXCEL_FILE = BASE_DIR / "portfolio.xlsx"

# Χρησιμοποιείται από create_portfolio_excel()
OUTPUT_FILE = BASE_DIR / "portfolio_updated.xlsx"


# ==========================================================
# ΣΤΗΛΕΣ EXCEL
# ==========================================================

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


# ==========================================================
# ΜΟΡΦΟΠΟΙΗΣΗ EXCEL
# ==========================================================

def format_portfolio_sheet(sheet):

    # Παγώνουμε την πρώτη γραμμή
    sheet.freeze_panes = "A2"

    # Φίλτρα στις στήλες
    sheet.auto_filter.ref = sheet.dimensions

    # Μορφοποίηση headers
    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9E1F2"
    )

    for cell in sheet[1]:

        cell.font = Font(bold=True)

        cell.fill = header_fill

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )

    # Βρίσκουμε τις στήλες
    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[header] = cell.column

    # ------------------------------------------------------
    # Χρηματικές στήλες
    # ------------------------------------------------------

    money_fields = [
        "purchase_price",
        "current_price",
        "market_value",
    ]

    for field in money_fields:

        if field not in headers:
            continue

        column = headers[field]

        for row in range(
            2,
            sheet.max_row + 1
        ):

            sheet.cell(
                row=row,
                column=column
            ).number_format = '#,##0.00 "€"'

    # ------------------------------------------------------
    # Ποσοστά
    #
    # Οι τιμές μας είναι ήδη:
    # 12.50
    #
    # και όχι:
    # 0.125
    # ------------------------------------------------------

    percent_fields = [
        "percent_change",
        "monthly_percent_change",
        "portfolio_weight",
        "vuaa_return",
        "excess_return",
    ]

    for field in percent_fields:

        if field not in headers:
            continue

        column = headers[field]

        for row in range(
            2,
            sheet.max_row + 1
        ):

            sheet.cell(
                row=row,
                column=column
            ).number_format = '0.00"%"'

    # ------------------------------------------------------
    # Ποσότητα
    # ------------------------------------------------------

    if "quantity" in headers:

        column = headers["quantity"]

        for row in range(
            2,
            sheet.max_row + 1
        ):

            sheet.cell(
                row=row,
                column=column
            ).number_format = "0.########"

    # ------------------------------------------------------
    # Αυτόματο πλάτος στηλών
    # ------------------------------------------------------

    for column_cells in sheet.columns:

        max_length = 0

        column_letter = get_column_letter(
            column_cells[0].column
        )

        for cell in column_cells:

            if cell.value is None:
                continue

            cell_length = len(
                str(cell.value)
            )

            if cell_length > max_length:
                max_length = cell_length

        sheet.column_dimensions[
            column_letter
        ].width = min(
            max_length + 2,
            25
        )


# ==========================================================
# ΔΙΑΒΑΣΜΑ portfolio.xlsx
# ==========================================================

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

    # Βρίσκουμε τις στήλες
    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[header] = cell.column

    # Πρέπει να υπάρχει symbol
    if "symbol" not in headers:

        workbook.close()

        raise ValueError(
            "Δεν βρέθηκε στήλη 'symbol' στο Excel"
        )

    stocks = []

    # Διαβάζουμε όλες τις γραμμές
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

        stock = {
            "symbol": str(symbol).strip()
        }

        # Platform
        if "platform" in headers:

            stock["platform"] = sheet.cell(
                row=row,
                column=headers["platform"]
            ).value

        # Sector
        if "sector" in headers:

            stock["sector"] = sheet.cell(
                row=row,
                column=headers["sector"]
            ).value

        # Country
        if "country" in headers:

            stock["country"] = sheet.cell(
                row=row,
                column=headers["country"]
            ).value

        stocks.append(stock)

    workbook.close()

    return stocks


# ==========================================================
# SYMBOL LOOKUP
# ==========================================================

def get_symbol_lookup():

    stocks = get_excel_stocks()

    lookup = {}

    for stock in stocks:

        symbol = stock["symbol"].strip()

        # Πλήρες Yahoo ticker
        # RHM.DE -> RHM.DE
        lookup[
            symbol.upper()
        ] = symbol

        # Βασικό ticker
        # RHM.DE -> RHM
        base_symbol = symbol.split(".")[0]

        # RHM -> RHM.DE
        if base_symbol.upper() not in lookup:

            lookup[
                base_symbol.upper()
            ] = symbol

    return lookup


# ==========================================================
# ΔΗΜΙΟΥΡΓΙΑ ΝΕΟΥ EXCEL
# ==========================================================

def create_portfolio_excel(stocks):

    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Portfolio"

    # Headers
    sheet.append(HEADERS)

    # Γράφουμε τις θέσεις
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

    # Μορφοποίηση
    format_portfolio_sheet(sheet)

    # Αποθήκευση
    workbook.save(OUTPUT_FILE)

    workbook.close()

    return OUTPUT_FILE


# ==========================================================
# ΕΝΗΜΕΡΩΣΗ portfolio.xlsx
# ==========================================================

def update_portfolio_excel(stocks):

    # ------------------------------------------------------
    # Αν δεν υπάρχει Excel, το δημιουργούμε
    # ------------------------------------------------------

    if not EXCEL_FILE.exists():

        workbook = Workbook()

        sheet = workbook.active
        sheet.title = "Portfolio"

        sheet.append(HEADERS)

        workbook.save(EXCEL_FILE)
        workbook.close()

    # ------------------------------------------------------
    # Ανοίγουμε το υπάρχον Excel
    # ------------------------------------------------------

    workbook = load_workbook(EXCEL_FILE)

    sheet = workbook.worksheets[0]

    # ------------------------------------------------------
    # Βρίσκουμε τα headers
    # ------------------------------------------------------

    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[header] = cell.column

    # ------------------------------------------------------
    # Προσθέτουμε headers που λείπουν
    # ------------------------------------------------------

    for header in HEADERS:

        if header not in headers:

            new_column = sheet.max_column + 1

            sheet.cell(
                row=1,
                column=new_column
            ).value = header

            headers[header] = new_column

    # ======================================================
    # ΚΡΑΤΑΜΕ SECTOR / COUNTRY
    #
    # Το κλειδί είναι:
    #
    # (symbol, platform)
    #
    # ώστε:
    #
    # RHM.DE + Capital
    # RHM.DE + Freedom24
    #
    # να θεωρούνται διαφορετικές γραμμές.
    # ======================================================

    manual_data = {}

    for row in range(
        2,
        sheet.max_row + 1
    ):

        symbol = sheet.cell(
            row=row,
            column=headers["symbol"]
        ).value

        platform = sheet.cell(
            row=row,
            column=headers["platform"]
        ).value

        if not symbol:
            continue

        key = (
            str(symbol).strip().upper(),
            str(platform or "").strip().upper()
        )

        sector = sheet.cell(
            row=row,
            column=headers["sector"]
        ).value

        country = sheet.cell(
            row=row,
            column=headers["country"]
        ).value

        manual_data[key] = {
            "sector": sector,
            "country": country
        }

    # ======================================================
    # ΣΒΗΝΟΥΜΕ ΟΛΕΣ ΤΙΣ ΠΑΛΙΕΣ ΘΕΣΕΙΣ
    #
    # Κρατάμε μόνο την πρώτη γραμμή (headers).
    # ======================================================

    if sheet.max_row > 1:

        sheet.delete_rows(
            2,
            sheet.max_row - 1
        )

    # ======================================================
    # ΓΡΑΦΟΥΜΕ ΤΙΣ ΣΗΜΕΡΙΝΕΣ ΕΝΕΡΓΕΣ ΘΕΣΕΙΣ
    # ======================================================

    for stock in stocks:

        symbol = stock.get("symbol")
        platform = stock.get("platform")

        if not symbol:
            continue

        key = (
            str(symbol).strip().upper(),
            str(platform or "").strip().upper()
        )

        # --------------------------------------------------
        # Παίρνουμε τα παλιά χειροκίνητα στοιχεία
        # --------------------------------------------------

        old_manual_data = manual_data.get(
            key,
            {}
        )

        sector = old_manual_data.get(
            "sector"
        )

        country = old_manual_data.get(
            "country"
        )

        # --------------------------------------------------
        # Αν αργότερα έχουμε sector από API,
        # χρησιμοποιούμε τη νέα τιμή
        # --------------------------------------------------

        if stock.get("sector") is not None:

            sector = stock.get("sector")

        # --------------------------------------------------
        # Αν αργότερα έχουμε country από API,
        # χρησιμοποιούμε τη νέα τιμή
        # --------------------------------------------------

        if stock.get("country") is not None:

            country = stock.get("country")

        # --------------------------------------------------
        # Γράφουμε τη νέα γραμμή
        # --------------------------------------------------

        sheet.append([
            stock.get("symbol"),
            stock.get("name"),
            sector,
            country,
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

    # ======================================================
    # ΜΟΡΦΟΠΟΙΗΣΗ
    # ======================================================

    format_portfolio_sheet(sheet)

    # ======================================================
    # ΑΠΟΘΗΚΕΥΣΗ
    # ======================================================

    workbook.save(EXCEL_FILE)

    workbook.close()

    return EXCEL_FILE