from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


# ==========================================================
# ΑΡΧΕΙΑ
# ==========================================================

BASE_DIR = Path(__file__).resolve().parents[2]

EXCEL_FILE = BASE_DIR / "portfolio.xlsx"

OUTPUT_FILE = BASE_DIR / "portfolio_updated.xlsx"


# ==========================================================
# ΣΤΗΛΕΣ EXCEL
#
# ΠΡΟΣΟΧΗ:
# Η σειρά εδώ είναι η επίσημη σειρά του portfolio.
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
# ΑΦΑΙΡΕΣΗ ΠΑΛΙΩΝ EXCEL TABLES
# ==========================================================

def remove_existing_tables(sheet):

    table_names = list(
        sheet.tables.keys()
    )

    for table_name in table_names:

        del sheet.tables[
            table_name
        ]


# ==========================================================
# ΚΑΘΑΡΙΣΜΟΣ ΕΠΙΠΛΕΟΝ ΣΤΗΛΩΝ
#
# Κρατάμε μόνο A:O
# δηλαδή τις 15 στήλες του HEADERS.
# ==========================================================

def remove_extra_columns(sheet):

    wanted_columns = len(
        HEADERS
    )

    if sheet.max_column > wanted_columns:

        columns_to_delete = (
            sheet.max_column
            - wanted_columns
        )

        sheet.delete_cols(
            wanted_columns + 1,
            columns_to_delete
        )


# ==========================================================
# ΕΠΙΒΟΛΗ ΣΩΣΤΗΣ ΣΕΙΡΑΣ HEADERS
# ==========================================================

def write_correct_headers(sheet):

    for column, header in enumerate(
        HEADERS,
        start=1
    ):

        sheet.cell(
            row=1,
            column=column
        ).value = header


# ==========================================================
# EXCEL TABLE
# ==========================================================

def create_stock_table(sheet):

    # Αν δεν υπάρχουν μετοχές,
    # δεν δημιουργούμε Table.
    if sheet.max_row < 2:
        return

    last_column = get_column_letter(
        len(HEADERS)
    )

    table_reference = (
        f"A1:{last_column}{sheet.max_row}"
    )

    table = Table(
        displayName="StockSummary",
        ref=table_reference
    )

    style = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )

    table.tableStyleInfo = style

    sheet.add_table(
        table
    )


# ==========================================================
# ΜΟΡΦΟΠΟΙΗΣΗ EXCEL
# ==========================================================

def format_portfolio_sheet(sheet):

    # ------------------------------------------------------
    # Freeze header
    # ------------------------------------------------------

    sheet.freeze_panes = "A2"

    # ------------------------------------------------------
    # Header
    # ------------------------------------------------------

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9E1F2"
    )

    for cell in sheet[1]:

        cell.font = Font(
            bold=True
        )

        cell.fill = header_fill

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )

    sheet.row_dimensions[1].height = 24

    # ------------------------------------------------------
    # Header lookup
    # ------------------------------------------------------

    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[
                header
            ] = cell.column

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

        column = headers[
            field
        ]

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
    # Οι τιμές είναι ήδη:
    #
    # 2.03
    #
    # και όχι:
    #
    # 0.0203
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

        column = headers[
            field
        ]

        for row in range(
            2,
            sheet.max_row + 1
        ):

            sheet.cell(
                row=row,
                column=column
            ).number_format = '0.00"%"'

    # ------------------------------------------------------
    # Quantity
    # ------------------------------------------------------

    if "quantity" in headers:

        column = headers[
            "quantity"
        ]

        for row in range(
            2,
            sheet.max_row + 1
        ):

            sheet.cell(
                row=row,
                column=column
            ).number_format = "0.########"

    # ------------------------------------------------------
    # Purchase date alignment
    # ------------------------------------------------------

    if "purchase_date" in headers:

        column = headers[
            "purchase_date"
        ]

        for row in range(
            2,
            sheet.max_row + 1
        ):

            sheet.cell(
                row=row,
                column=column
            ).alignment = Alignment(
                horizontal="center"
            )

    # ------------------------------------------------------
    # Αυτόματο πλάτος στηλών
    # ------------------------------------------------------

    for column_number in range(
        1,
        len(HEADERS) + 1
    ):

        max_length = 0

        for row in range(
            1,
            sheet.max_row + 1
        ):

            cell = sheet.cell(
                row=row,
                column=column_number
            )

            if cell.value is None:
                continue

            length = len(
                str(cell.value)
            )

            if length > max_length:
                max_length = length

        column_letter = get_column_letter(
            column_number
        )

        sheet.column_dimensions[
            column_letter
        ].width = min(
            max_length + 2,
            25
        )

    # ------------------------------------------------------
    # Excel Table
    # ------------------------------------------------------

    create_stock_table(
        sheet
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

    headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            headers[
                header
            ] = cell.column

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

        stock = {
            "symbol": str(
                symbol
            ).strip()
        }

        if "platform" in headers:

            stock["platform"] = sheet.cell(
                row=row,
                column=headers["platform"]
            ).value

        if "sector" in headers:

            stock["sector"] = sheet.cell(
                row=row,
                column=headers["sector"]
            ).value

        if "country" in headers:

            stock["country"] = sheet.cell(
                row=row,
                column=headers["country"]
            ).value

        stocks.append(
            stock
        )

    workbook.close()

    return stocks


# ==========================================================
# SYMBOL LOOKUP
# ==========================================================

def get_symbol_lookup():

    stocks = get_excel_stocks()

    lookup = {}

    for stock in stocks:

        symbol = stock[
            "symbol"
        ].strip()

        # Πλήρες ticker
        lookup[
            symbol.upper()
        ] = symbol

        # Βασικό ticker
        base_symbol = symbol.split(
            "."
        )[0]

        if base_symbol.upper() not in lookup:

            lookup[
                base_symbol.upper()
            ] = symbol

    return lookup


# ==========================================================
# ΔΗΜΙΟΥΡΓΙΑ portfolio_updated.xlsx
# ==========================================================

def create_portfolio_excel(stocks):

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Portfolio"

    # ------------------------------------------------------
    # Headers
    # ------------------------------------------------------

    sheet.append(
        HEADERS
    )

    # ------------------------------------------------------
    # Data
    # ------------------------------------------------------

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

    format_portfolio_sheet(
        sheet
    )

    workbook.save(
        OUTPUT_FILE
    )

    workbook.close()

    return OUTPUT_FILE


# ==========================================================
# ΕΝΗΜΕΡΩΣΗ portfolio.xlsx
# ==========================================================

def update_portfolio_excel(stocks):

    # ------------------------------------------------------
    # Αν δεν υπάρχει το αρχείο,
    # δημιουργούμε νέο.
    # ------------------------------------------------------

    if not EXCEL_FILE.exists():

        workbook = Workbook()

        sheet = workbook.active

        sheet.title = "Portfolio"

        sheet.append(
            HEADERS
        )

        workbook.save(
            EXCEL_FILE
        )

        workbook.close()

    # ------------------------------------------------------
    # Ανοίγουμε το υπάρχον Excel
    # ------------------------------------------------------

    workbook = load_workbook(
        EXCEL_FILE
    )

    sheet = workbook.worksheets[0]

    # ------------------------------------------------------
    # Βρίσκουμε την ΠΑΛΙΑ σειρά headers.
    #
    # Το χρειαζόμαστε μόνο για να κρατήσουμε
    # τα χειροκίνητα sector/country.
    # ------------------------------------------------------

    old_headers = {}

    for cell in sheet[1]:

        if cell.value:

            header = str(
                cell.value
            ).strip().lower()

            old_headers[
                header
            ] = cell.column

    # ======================================================
    # ΚΡΑΤΑΜΕ MANUAL SECTOR / COUNTRY
    # ======================================================

    manual_data = {}

    if (
        "symbol" in old_headers
        and "platform" in old_headers
    ):

        for row in range(
            2,
            sheet.max_row + 1
        ):

            symbol = sheet.cell(
                row=row,
                column=old_headers["symbol"]
            ).value

            platform = sheet.cell(
                row=row,
                column=old_headers["platform"]
            ).value

            if not symbol:
                continue

            key = (
                str(
                    symbol
                ).strip().upper(),

                str(
                    platform or ""
                ).strip().upper()
            )

            sector = None
            country = None

            if "sector" in old_headers:

                sector = sheet.cell(
                    row=row,
                    column=old_headers["sector"]
                ).value

            if "country" in old_headers:

                country = sheet.cell(
                    row=row,
                    column=old_headers["country"]
                ).value

            manual_data[
                key
            ] = {
                "sector": sector,
                "country": country
            }

    # ======================================================
    # ΚΑΘΑΡΙΖΟΥΜΕ ΤΟ ΠΑΛΙΟ TABLE
    # ======================================================

    remove_existing_tables(
        sheet
    )

    # ======================================================
    # ΣΒΗΝΟΥΜΕ ΟΛΕΣ ΤΙΣ ΠΑΛΙΕΣ ΘΕΣΕΙΣ
    # ======================================================

    if sheet.max_row > 1:

        sheet.delete_rows(
            2,
            sheet.max_row - 1
        )

    # ======================================================
    # ΚΑΘΑΡΙΖΟΥΜΕ ΤΙΣ ΠΕΡΙΤΤΕΣ ΣΤΗΛΕΣ
    #
    # Αυτό θα αφαιρέσει:
    #
    # Στήλη1
    # Στήλη2
    # ...
    # μέχρι XFD
    # ======================================================

    remove_extra_columns(
        sheet
    )

    # ======================================================
    # ΒΑΖΟΥΜΕ HEADERS ΑΚΡΙΒΩΣ ΣΤΗ ΣΩΣΤΗ ΣΕΙΡΑ
    # ======================================================

    write_correct_headers(
        sheet
    )

    # ======================================================
    # ΓΡΑΦΟΥΜΕ ΤΙΣ ΣΗΜΕΡΙΝΕΣ ΘΕΣΕΙΣ
    # ======================================================

    for stock in stocks:

        symbol = stock.get(
            "symbol"
        )

        platform = stock.get(
            "platform"
        )

        if not symbol:
            continue

        key = (
            str(
                symbol
            ).strip().upper(),

            str(
                platform or ""
            ).strip().upper()
        )

        # --------------------------------------------------
        # Παλιό manual sector/country
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
        # Αν Yahoo/API δίνει sector,
        # αυτό έχει προτεραιότητα.
        # --------------------------------------------------

        if stock.get(
            "sector"
        ) is not None:

            sector = stock.get(
                "sector"
            )

        # --------------------------------------------------
        # Αν Yahoo/API δίνει country,
        # αυτό έχει προτεραιότητα.
        # --------------------------------------------------

        if stock.get(
            "country"
        ) is not None:

            country = stock.get(
                "country"
            )

        # --------------------------------------------------
        # ΠΡΟΣΟΧΗ:
        #
        # Η σειρά είναι ΑΚΡΙΒΩΣ ίδια με HEADERS.
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
    # ΜΟΡΦΟΠΟΙΗΣΗ + ΝΕΟ STOCKSUMMARY
    # ======================================================

    format_portfolio_sheet(
        sheet
    )

    # ======================================================
    # ΑΠΟΘΗΚΕΥΣΗ
    # ======================================================

    workbook.save(
        EXCEL_FILE
    )

    workbook.close()

    return EXCEL_FILE