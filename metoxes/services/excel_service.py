from pathlib import Path
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.table import Table, TableStyleInfo


BASE_DIR = Path(__file__).resolve().parents[2]
EXCEL_FILE = BASE_DIR / "portfolio.xlsx"
OUTPUT_FILE = BASE_DIR / "portfolio_updated.xlsx"

SOLD_SHEET_NAME = "Sold"
SOLD_TABLE_NAME = "SoldSummary"

# Βασικές στήλες του portfolio.xlsx
CORE_HEADERS = [
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
    "avg_monthly_change",
    "portfolio_weight",
    "vuaa_return",
    "excess_return",
]

# Προαιρετικές στήλες. Δεν προστίθενται αν δεν υπάρχουν ήδη
# ή αν δεν έρχονται πραγματικά δεδομένα για αυτές.
OPTIONAL_HEADERS = [
    "fcf_yield",
    "fcf_growth",
    "roic",
    "final_score",
]

# Παραμένει διαθέσιμο για συμβατότητα με τυχόν imports από άλλο module.
HEADERS = CORE_HEADERS + OPTIONAL_HEADERS


# ==========================================================
# ΒΑΣΙΚΑ HELPERS
# ==========================================================

def normalize_excel_date(value):
    """
    Μετατρέπει την purchase_date σε πραγματική ημερομηνία Excel.

    Αυτό είναι προτιμότερο από το να γράφεται η ημερομηνία ως text
    ή ως τύπος DATEVALUE, γιατί το Excel τότε αναγνωρίζει απευθείας
    τη στήλη ως ημερομηνία και ενεργοποιεί τα Date Filters.
    """
    if value in (None, ""):
        return None

    # Ήδη σωστός τύπος ημερομηνίας.
    if isinstance(value, datetime):
        return value.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    if isinstance(value, date):
        return datetime(
            value.year,
            value.month,
            value.day
        )

    # Αν έρθει Excel serial number, το αφήνουμε ως έχει.
    # Με number_format dd/mm/yyyy το Excel το χειρίζεται ως ημερομηνία.
    if isinstance(value, (int, float)):
        return value

    text = str(value).strip()

    if not text:
        return None

    # Πρώτα δοκιμάζουμε ISO μορφές, π.χ.
    # 2026-09-26 ή 2026-09-26T14:30:00.
    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        return parsed.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=None
        )
    except ValueError:
        pass

    # Συνήθεις μορφές που μπορεί να έρχονται από brokers / API.
    date_formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y",
    )

    for date_format in date_formats:
        try:
            return datetime.strptime(
                text,
                date_format
            )
        except ValueError:
            continue

    # Αν δεν αναγνωρίζεται, δεν καταστρέφουμε την αρχική τιμή.
    # Θα παραμείνει text ώστε να είναι ορατό τι ακριβώς ήρθε.
    return value


def calculate_avg_monthly_change(percent_change, purchase_date, as_of_date=None):
    """
    Απλός μέσος μηνιαίος ρυθμός μεταβολής, όπως ζήτησε ο χρήστης:

        avg_monthly_change = percent_change / μήνες κατοχής

    Παράδειγμα:
        +30% συνολική μεταβολή σε 3 μήνες -> +10% / μήνα.

    ΣΗΜΕΙΩΣΗ:
    Δεν είναι σύνθετος/ανατοκισμένος μηνιαίος ρυθμός (CAGR).
    Χρησιμοποιούμε ολοκληρωμένους ημερολογιακούς μήνες και ελάχιστο
    παρονομαστή 1, ώστε μία θέση μικρότερη του ενός μήνα να μη δίνει
    διαίρεση με το μηδέν.
    """
    if percent_change in (None, "") or purchase_date in (None, ""):
        return None

    try:
        change = float(percent_change)
    except (TypeError, ValueError):
        return None

    parsed_date = normalize_excel_date(purchase_date)

    # Η normalize_excel_date μπορεί να επιστρέψει αρχικό text όταν
    # δεν μπορεί να το αναγνωρίσει. Σε αυτή την περίπτωση δεν κάνουμε
    # αυθαίρετο υπολογισμό.
    if isinstance(parsed_date, datetime):
        purchase_dt = parsed_date.date()
    elif isinstance(parsed_date, date):
        purchase_dt = parsed_date
    else:
        return None

    today = as_of_date or date.today()

    if isinstance(today, datetime):
        today = today.date()

    # Μελλοντική ημερομηνία αγοράς -> δεν υπάρχει έγκυρη διάρκεια.
    if purchase_dt > today:
        return None

    months = (
        (today.year - purchase_dt.year) * 12
        + (today.month - purchase_dt.month)
    )

    # Μετράμε μόνο ολοκληρωμένους μήνες.
    if today.day < purchase_dt.day:
        months -= 1

    months = max(1, months)

    return round(change / months, 2)


def get_header_lookup(sheet):
    headers = {}

    for cell in sheet[1]:
        if cell.value is None:
            continue

        headers[
            str(cell.value).strip().lower()
        ] = cell.column

    return headers


def get_active_headers(stocks=None, sheet=None):
    """
    Κρατάει πάντα τις 15 βασικές στήλες του portfolio.

    Οι προαιρετικές fcf/roic/final_score μπαίνουν μόνο αν:
    1) υπάρχουν ήδη στο υπάρχον Excel ή
    2) έρχεται τουλάχιστον μία μη κενή τιμή από τα stocks.

    Έτσι το τωρινό portfolio A:O δεν μεγαλώνει χωρίς λόγο.
    """
    active_headers = list(CORE_HEADERS)

    existing_headers = set()
    if sheet is not None:
        existing_headers = set(
            get_header_lookup(sheet).keys()
        )

    stocks = stocks or []

    for header in OPTIONAL_HEADERS:
        exists_in_sheet = header in existing_headers

        has_incoming_value = any(
            stock.get(header) not in (None, "")
            for stock in stocks
        )

        if exists_in_sheet or has_incoming_value:
            active_headers.append(header)

    return active_headers


def remove_existing_tables(sheet):
    for table_name in list(sheet.tables.keys()):
        del sheet.tables[table_name]


def remove_existing_merges(sheet):
    for merged_range in list(sheet.merged_cells.ranges):
        sheet.unmerge_cells(str(merged_range))


def clear_conditional_formatting(sheet):
    sheet.conditional_formatting = ConditionalFormattingList()


def clear_sheet_auto_filter(sheet):
    """
    Σβήνει το παλιό απλό AutoFilter του worksheet.
    Το νέο φίλτρο θα ανήκει στο Excel Table StockSummary.
    """
    sheet.auto_filter = AutoFilter()


def remove_extra_columns(sheet, active_headers):
    wanted_columns = len(active_headers)

    if sheet.max_column > wanted_columns:
        sheet.delete_cols(
            wanted_columns + 1,
            sheet.max_column - wanted_columns
        )


def write_correct_headers(sheet, active_headers):
    for column, header in enumerate(
        active_headers,
        start=1
    ):
        sheet.cell(
            row=1,
            column=column
        ).value = header


def set_excel_recalculation(workbook):
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True


# ==========================================================
# EXCEL TABLE
# ==========================================================

def create_stock_table(
    sheet,
    last_data_row,
    active_headers,
    table_name="StockSummary"
):
    if last_data_row < 2:
        return

    last_column = get_column_letter(
        len(active_headers)
    )

    table = Table(
        displayName=table_name,
        ref=f"A1:{last_column}{last_data_row}"
    )

    # Ίδιο στυλ με το ΑΝΤΙΓΡΑΦΟ.
    style = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )

    table.tableStyleInfo = style
    sheet.add_table(table)


# ==========================================================
# CONDITIONAL FORMATTING
# ==========================================================

def add_monthly_change_conditional_formatting(
    sheet,
    last_data_row,
    active_headers
):
    if last_data_row < 2:
        return

    headers = get_header_lookup(sheet)
    monthly_column = headers.get(
        "monthly_percent_change"
    )

    if monthly_column is None:
        return

    monthly_letter = get_column_letter(
        monthly_column
    )

    last_column_letter = get_column_letter(
        len(active_headers)
    )

    # Όπως πριν, το symbol μένει εκτός του χρωματισμού.
    data_range = (
        f"B2:{last_column_letter}{last_data_row}"
    )

    peach_fill = PatternFill(
        fill_type="solid",
        fgColor="FCE4D6"
    )
    white_fill = PatternFill(
        fill_type="solid",
        fgColor="FFFFFF"
    )
    light_green_fill = PatternFill(
        fill_type="solid",
        fgColor="E2F0D9"
    )
    medium_green_fill = PatternFill(
        fill_type="solid",
        fgColor="A9D18E"
    )
    dark_green_fill = PatternFill(
        fill_type="solid",
        fgColor="70AD47"
    )

    sheet.conditional_formatting.add(
        data_range,
        FormulaRule(
            formula=[
                f'AND(${monthly_letter}2>=-4.99,'
                f'${monthly_letter}2<0)'
            ],
            fill=peach_fill
        )
    )

    sheet.conditional_formatting.add(
        data_range,
        FormulaRule(
            formula=[
                f'AND(${monthly_letter}2>=0,'
                f'${monthly_letter}2<2)'
            ],
            fill=white_fill
        )
    )

    sheet.conditional_formatting.add(
        data_range,
        FormulaRule(
            formula=[
                f'AND(${monthly_letter}2>=2,'
                f'${monthly_letter}2<4)'
            ],
            fill=light_green_fill
        )
    )

    sheet.conditional_formatting.add(
        data_range,
        FormulaRule(
            formula=[
                f'AND(${monthly_letter}2>=4,'
                f'${monthly_letter}2<=9)'
            ],
            fill=medium_green_fill
        )
    )

    sheet.conditional_formatting.add(
        data_range,
        FormulaRule(
            formula=[
                f'${monthly_letter}2>9'
            ],
            fill=dark_green_fill
        )
    )


# ==========================================================
# ΜΟΡΦΟΠΟΙΗΣΗ PORTFOLIO
# ==========================================================

def format_portfolio_sheet(
    sheet,
    last_data_row,
    active_headers,
    table_name="StockSummary"
):
    sheet.freeze_panes = "A2"

    # Καθαρίζουμε τυχόν hidden rows που είχαν μείνει
    # από παλιό φίλτρο του αρχείου.
    for row in range(2, last_data_row + 1):
        sheet.row_dimensions[row].hidden = False

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="4472C4"
    )

    header_border = Border(
        bottom=Side(
            style="thin",
            color="D9E2F3"
        )
    )

    for column_number in range(
        1,
        len(active_headers) + 1
    ):
        cell = sheet.cell(
            row=1,
            column=column_number
        )

        cell.font = Font(
            bold=True,
            color="FFFFFF"
        )
        cell.fill = header_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )
        cell.border = header_border

    sheet.row_dimensions[1].height = 24

    headers = get_header_lookup(sheet)

    # ------------------------------------------------------
    # MONEY
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

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column
            ).number_format = '#,##0.00 "€"'

    # ------------------------------------------------------
    # PERCENTAGES
    # Οι τιμές στα data είναι ήδη π.χ. 5.30 = 5.30%.
    # ------------------------------------------------------
    percent_fields = [
        "percent_change",
        "monthly_percent_change",
        "avg_monthly_change",
        "portfolio_weight",
        "vuaa_return",
        "excess_return",
        "fcf_yield",
        "fcf_growth",
        "roic",
    ]

    for field in percent_fields:
        if field not in headers:
            continue

        column = headers[field]

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column
            ).number_format = '0.00"%"'

    if "final_score" in headers:
        column = headers["final_score"]

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column
            ).number_format = "0.00"

    if "quantity" in headers:
        column = headers["quantity"]

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column
            ).number_format = "0.########"

    if "purchase_date" in headers:
        column = headers["purchase_date"]

        for row in range(2, last_data_row + 1):
            cell = sheet.cell(
                row=row,
                column=column
            )

            # Μετατροπή από text σε πραγματική Excel date.
            # Έτσι λειτουργούν σωστά τα Date Filters.
            cell.value = normalize_excel_date(
                cell.value
            )

            cell.number_format = "dd/mm/yyyy"
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

    # ------------------------------------------------------
    # ALIGNMENT
    # ------------------------------------------------------
    center_fields = [
        "symbol",
        "sector",
        "country",
        "platform",
        "quantity",
        "percent_change",
        "monthly_percent_change",
        "avg_monthly_change",
        "portfolio_weight",
        "vuaa_return",
        "excess_return",
        "fcf_yield",
        "fcf_growth",
        "roic",
        "final_score",
    ]

    for field in center_fields:
        if field not in headers:
            continue

        column = headers[field]

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column
            ).alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

    # ------------------------------------------------------
    # WIDTHS
    # ------------------------------------------------------
    column_widths = {
        "symbol": 12,
        "name": 38,
        "sector": 22,
        "country": 18,
        "platform": 13,
        "purchase_date": 15,
        "purchase_price": 16,
        "quantity": 12,
        "current_price": 16,
        "market_value": 16,
        "percent_change": 17,
        "monthly_percent_change": 25,
        "avg_monthly_change": 22,
        "portfolio_weight": 18,
        "vuaa_return": 14,
        "excess_return": 15,
        "fcf_yield": 14,
        "fcf_growth": 15,
        "roic": 12,
        "final_score": 14,
    }

    for field, width in column_widths.items():
        if field not in headers:
            continue

        column_letter = get_column_letter(
            headers[field]
        )

        sheet.column_dimensions[
            column_letter
        ].width = width

    create_stock_table(
        sheet,
        last_data_row,
        active_headers,
        table_name=table_name
    )

    add_monthly_change_conditional_formatting(
        sheet,
        last_data_row,
        active_headers
    )


# ==========================================================
# ΚΟΥΤΑΚΙΑ / SUMMARY - ΠΡΟΤΥΠΟ ΑΝΤΙΓΡΑΦΟ
# ==========================================================

def create_summary_boxes(
    sheet,
    last_data_row
):
    if last_data_row < 2:
        return

    # Στο ΑΝΤΙΓΡΑΦΟ:
    # τελευταίο data row 74 -> τίτλοι row 80 -> τιμές row 81.
    title_row = last_data_row + 6
    value_row = title_row + 1

    # PORTFOLIO RETURN: E:F
    sheet.merge_cells(
        start_row=title_row,
        start_column=5,
        end_row=title_row,
        end_column=6
    )
    sheet.merge_cells(
        start_row=value_row,
        start_column=5,
        end_row=value_row,
        end_column=6
    )

    # VUAA RETURN: I:J
    sheet.merge_cells(
        start_row=title_row,
        start_column=9,
        end_row=title_row,
        end_column=10
    )
    sheet.merge_cells(
        start_row=value_row,
        start_column=9,
        end_row=value_row,
        end_column=10
    )

    # ------------------------------------------------------
    # TITLES
    # ------------------------------------------------------
    sheet.cell(
        row=title_row,
        column=2
    ).value = "PORTFOLIO VALUE"

    sheet.cell(
        row=title_row,
        column=5
    ).value = "PORTFOLIO RETURN"

    sheet.cell(
        row=title_row,
        column=9
    ).value = "VUAA RETURN"

    sheet.cell(
        row=title_row,
        column=12
    ).value = "EXCESS RETURN"

    # ------------------------------------------------------
    # 1. PORTFOLIO VALUE
    # Ίδιος μηχανισμός με το ΑΝΤΙΓΡΑΦΟ:
    # visible current_price * quantity.
    # Το SUBTOTAL(109, OFFSET(...)) αγνοεί filtered rows.
    # ------------------------------------------------------
    sheet.cell(
        row=value_row,
        column=2
    ).value = (
        '=IFERROR('
        'SUMPRODUCT('
        'SUBTOTAL(109,OFFSET('
        'INDEX(StockSummary[current_price],1),'
        'ROW(StockSummary[current_price])-'
        'MIN(ROW(StockSummary[current_price])),'
        '0,1'
        ')),'
        'StockSummary[quantity]'
        '),'
        '0)'
    )

    # ------------------------------------------------------
    # 2. PORTFOLIO RETURN
    # Ίδιος τύπος με το ΑΝΤΙΓΡΑΦΟ:
    # Σ visible current value / Σ visible purchase value - 1.
    # ------------------------------------------------------
    sheet.cell(
        row=value_row,
        column=5
    ).value = (
        '=IFERROR('
        'SUMPRODUCT('
        'SUBTOTAL(103,OFFSET('
        'INDEX(StockSummary[symbol],1),'
        'ROW(StockSummary[symbol])-'
        'MIN(ROW(StockSummary[symbol])),'
        '0,1'
        ')),'
        'StockSummary[current_price],'
        'StockSummary[quantity]'
        ')'
        '/'
        'SUMPRODUCT('
        'SUBTOTAL(103,OFFSET('
        'INDEX(StockSummary[symbol],1),'
        'ROW(StockSummary[symbol])-'
        'MIN(ROW(StockSummary[symbol])),'
        '0,1'
        ')),'
        'StockSummary[purchase_price],'
        'StockSummary[quantity]'
        ')'
        '-1,'
        '0)'
    )

    # ------------------------------------------------------
    # 3. VUAA RETURN
    # Σταθμισμένος μέσος με portfolio_weight.
    # Τα vuaa_return/portfolio_weight είναι σε μονάδες %, γι' αυτό /100.
    # ------------------------------------------------------
    sheet.cell(
        row=value_row,
        column=9
    ).value = (
        '=IFERROR('
        'SUMPRODUCT('
        'SUBTOTAL(103,OFFSET('
        'INDEX(StockSummary[symbol],1),'
        'ROW(StockSummary[symbol])-'
        'MIN(ROW(StockSummary[symbol])),'
        '0,1'
        ')),'
        'StockSummary[portfolio_weight],'
        'StockSummary[vuaa_return]'
        ')'
        '/'
        'SUMPRODUCT('
        'SUBTOTAL(103,OFFSET('
        'INDEX(StockSummary[symbol],1),'
        'ROW(StockSummary[symbol])-'
        'MIN(ROW(StockSummary[symbol])),'
        '0,1'
        ')),'
        'StockSummary[portfolio_weight]'
        ')'
        '/100,'
        '0)'
    )

    # ------------------------------------------------------
    # 4. EXCESS RETURN
    # ------------------------------------------------------
    sheet.cell(
        row=value_row,
        column=12
    ).value = (
        f"=E{value_row}-I{value_row}"
    )

    # ------------------------------------------------------
    # COLORS - όπως στο ΑΝΤΙΓΡΑΦΟ
    # ------------------------------------------------------
    yellow_fill = PatternFill(
        fill_type="solid",
        fgColor="FFFF00"
    )
    gray_fill = PatternFill(
        fill_type="solid",
        fgColor="D9D9D9"
    )
    blue_fill = PatternFill(
        fill_type="solid",
        fgColor="B4C6E7"
    )
    peach_fill = PatternFill(
        fill_type="solid",
        fgColor="FCE4D6"
    )

    medium_black = Side(
        style="medium",
        color="000000"
    )

    # Το κίτρινο PORTFOLIO VALUE έχει περίγραμμα όπως στο αντίγραφο.
    title_border = Border(
        top=medium_black,
        left=medium_black,
        right=medium_black
    )
    value_border = Border(
        bottom=medium_black,
        left=medium_black,
        right=medium_black
    )

    # ------------------------------------------------------
    # PORTFOLIO VALUE - B
    # ------------------------------------------------------
    for row in [title_row, value_row]:
        cell = sheet.cell(
            row=row,
            column=2
        )
        cell.fill = yellow_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )
        cell.font = Font(
            bold=False,
            color="000000"
        )

    sheet.cell(
        row=title_row,
        column=2
    ).border = title_border

    sheet.cell(
        row=value_row,
        column=2
    ).border = value_border

    sheet.cell(
        row=value_row,
        column=2
    ).number_format = '#,##0.00 "€"'

    # ------------------------------------------------------
    # PORTFOLIO RETURN - E:F
    # ------------------------------------------------------
    for row in [title_row, value_row]:
        for column in range(5, 7):
            cell = sheet.cell(
                row=row,
                column=column
            )
            cell.fill = gray_fill
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )
            cell.font = Font(
                bold=False,
                color="000000"
            )

    sheet.cell(
        row=title_row,
        column=5
    ).border = Border(
        top=medium_black
    )

    sheet.cell(
        row=value_row,
        column=5
    ).number_format = "0.00%"

    # ------------------------------------------------------
    # VUAA RETURN - I:J
    # ------------------------------------------------------
    for row in [title_row, value_row]:
        for column in range(9, 11):
            cell = sheet.cell(
                row=row,
                column=column
            )
            cell.fill = blue_fill
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )
            cell.font = Font(
                bold=False,
                color="000000"
            )

    sheet.cell(
        row=title_row,
        column=9
    ).border = Border(
        top=medium_black
    )

    sheet.cell(
        row=value_row,
        column=9
    ).number_format = "0.00%"

    # ------------------------------------------------------
    # EXCESS RETURN - L
    # ------------------------------------------------------
    for row in [title_row, value_row]:
        cell = sheet.cell(
            row=row,
            column=12
        )
        cell.fill = peach_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )
        cell.font = Font(
            bold=False,
            color="000000"
        )

    sheet.cell(
        row=value_row,
        column=12
    ).number_format = "0.00%"

    sheet.row_dimensions[title_row].height = 21
    sheet.row_dimensions[value_row].height = 21


# ==========================================================
# ΔΙΑΒΑΣΜΑ STOCKS ΑΠΟ portfolio.xlsx
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
    headers = get_header_lookup(sheet)

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

        # Τα summary boxes έχουν κενό symbol,
        # άρα αγνοούνται αυτόματα.
        if not symbol:
            continue

        stock = {
            "symbol": str(symbol).strip()
        }

        for field in [
            "platform",
            "sector",
            "country",
        ]:
            if field in headers:
                stock[field] = sheet.cell(
                    row=row,
                    column=headers[field]
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

        # Πλήρες ticker: RHM.DE -> RHM.DE
        lookup[
            symbol.upper()
        ] = symbol

        # Βασικό ticker: RHM -> RHM.DE
        base_symbol = symbol.split(".")[0]

        if base_symbol.upper() not in lookup:
            lookup[
                base_symbol.upper()
            ] = symbol

    return lookup


# ==========================================================
# STOCK -> EXCEL ROW
# ==========================================================

def stock_to_excel_row(
    stock,
    active_headers,
    sector=None,
    country=None
):
    values = {
        "symbol": stock.get("symbol"),
        "name": stock.get("name"),
        "sector": (
            stock.get("sector")
            if sector is None
            else sector
        ),
        "country": (
            stock.get("country")
            if country is None
            else country
        ),
        "platform": stock.get("platform"),
        "purchase_date": normalize_excel_date(
            stock.get("purchase_date")
        ),
        "purchase_price": stock.get("purchase_price"),
        "quantity": stock.get("quantity"),
        "current_price": stock.get("current_price"),
        "market_value": stock.get("market_value"),
        "percent_change": stock.get("percent_change"),
        "monthly_percent_change": stock.get(
            "monthly_percent_change"
        ),
        "avg_monthly_change": calculate_avg_monthly_change(
            stock.get("percent_change"),
            stock.get("purchase_date")
        ),
        "portfolio_weight": stock.get("portfolio_weight"),
        "vuaa_return": stock.get("vuaa_return"),
        "excess_return": stock.get("excess_return"),
        "fcf_yield": stock.get("fcf_yield"),
        "fcf_growth": stock.get("fcf_growth"),
        "roic": stock.get("roic"),
        "final_score": stock.get("final_score"),
    }

    return [
        values.get(header)
        for header in active_headers
    ]


# ==========================================================
# ΔΗΜΙΟΥΡΓΙΑ portfolio_updated.xlsx
# ==========================================================

def create_portfolio_excel(stocks):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Portfolio"

    active_headers = get_active_headers(
        stocks=stocks
    )

    sheet.append(active_headers)

    for stock in stocks:
        if not stock.get("symbol"):
            continue

        sheet.append(
            stock_to_excel_row(
                stock,
                active_headers
            )
        )

    last_data_row = sheet.max_row

    format_portfolio_sheet(
        sheet,
        last_data_row,
        active_headers
    )

    create_summary_boxes(
        sheet,
        last_data_row
    )

    set_excel_recalculation(workbook)

    workbook.save(OUTPUT_FILE)
    workbook.close()

    return OUTPUT_FILE


# ==========================================================
# ΠΩΛΗΜΕΝΕΣ ΘΕΣΕΙΣ - 2ο ΦΥΛΛΟ "Sold"
# ==========================================================

def normalize_position_key(symbol, platform):
    """
    Μοναδικό κλειδί θέσης μέσα στο portfolio.
    Ίδιο symbol σε διαφορετικό broker = διαφορετική θέση.
    """
    return (
        str(symbol or "").strip().upper(),
        str(platform or "").strip().upper(),
    )


def get_headers_in_order(sheet):
    """
    Επιστρέφει τα headers ακριβώς με τη σειρά που υπάρχουν
    στη γραμμή 1 του φύλλου.
    """
    headers = []

    for cell in sheet[1]:
        if cell.value in (None, ""):
            continue

        headers.append(
            str(cell.value).strip().lower()
        )

    return headers


def collect_portfolio_rows(sheet):
    """
    Διαβάζει τις πραγματικές γραμμές του Portfolio ΠΡΙΝ
    ξαναγραφτεί το φύλλο.

    Κρατάμε όλα τα στοιχεία της παλιάς γραμμής ώστε, αν
    η θέση έχει πουληθεί, να μεταφερθεί στο Sold ακριβώς
    όπως ήταν στην τελευταία ενημέρωση του portfolio.xlsx.
    """
    headers = get_header_lookup(sheet)
    header_order = get_headers_in_order(sheet)

    if "symbol" not in headers:
        return [], header_order

    rows = []

    for row_number in range(2, sheet.max_row + 1):
        symbol = sheet.cell(
            row=row_number,
            column=headers["symbol"]
        ).value

        # Αγνοούμε κενές γραμμές και summary boxes.
        if not symbol:
            continue

        row_data = {}

        for header in header_order:
            column = headers.get(header)

            if column is None:
                continue

            row_data[header] = sheet.cell(
                row=row_number,
                column=column
            ).value

        rows.append(row_data)

    return rows, header_order


def ensure_sold_sheet_headers(
    sold_sheet,
    source_headers
):
    """
    Το Sold κρατά τις ίδιες στήλες με το Portfolio.

    Αν αργότερα προστεθούν fcf_yield / fcf_growth / roic /
    final_score, προστίθενται και στο Sold χωρίς να χαθούν
    οι παλιότερες πωλημένες γραμμές.
    """
    existing_headers = get_headers_in_order(
        sold_sheet
    )

    # Νέο / άδειο φύλλο.
    if not existing_headers:
        for column, header in enumerate(
            source_headers,
            start=1
        ):
            sold_sheet.cell(
                row=1,
                column=column
            ).value = header

        return list(source_headers)

    # Προσθέτουμε μόνο headers που λείπουν.
    for header in source_headers:
        if header in existing_headers:
            continue

        new_column = len(existing_headers) + 1

        sold_sheet.cell(
            row=1,
            column=new_column
        ).value = header

        existing_headers.append(header)

    return existing_headers


def archive_sold_positions(
    workbook,
    portfolio_sheet,
    stocks
):
    """
    Βρίσκει ποιες παλιές θέσεις εξαφανίστηκαν από τα νέα
    δεδομένα και τις μεταφέρει στο δεύτερο φύλλο "Sold".

    Πώληση θεωρούμε ότι έγινε όταν το ίδιο
    (symbol, platform) υπήρχε στο προηγούμενο Portfolio
    και ΔΕΝ υπάρχει καθόλου στα νέα stocks.

    Μερική πώληση (ίδιο key αλλά μικρότερη quantity)
    ΔΕΝ μετακινεί τη γραμμή στο Sold.
    """
    old_rows, source_headers = collect_portfolio_rows(
        portfolio_sheet
    )

    if not old_rows:
        return 0

    incoming_keys = {
        normalize_position_key(
            stock.get("symbol"),
            stock.get("platform")
        )
        for stock in stocks
        if stock.get("symbol")
    }

    sold_rows = []

    for row_data in old_rows:
        key = normalize_position_key(
            row_data.get("symbol"),
            row_data.get("platform")
        )

        if key not in incoming_keys:
            sold_rows.append(row_data)

    if not sold_rows:
        return 0

    # Δημιουργούμε το δεύτερο φύλλο μόνο όταν υπάρχει
    # πραγματικά πωλημένη θέση.
    if SOLD_SHEET_NAME in workbook.sheetnames:
        sold_sheet = workbook[SOLD_SHEET_NAME]

        # Το Sold πρέπει να είναι πάντα το 2ο φύλλο.
        current_index = workbook.index(sold_sheet)

        if current_index != 1:
            workbook.move_sheet(
                sold_sheet,
                offset=1 - current_index
            )
    else:
        sold_sheet = workbook.create_sheet(
            title=SOLD_SHEET_NAME,
            index=1
        )

    # Το Sold μπορεί ήδη να έχει Excel Table από προηγούμενη
    # ενημέρωση. Το αφαιρούμε προσωρινά, προσθέτουμε τις νέες
    # γραμμές και το ξαναδημιουργούμε με σωστό range.
    remove_existing_tables(sold_sheet)
    remove_existing_merges(sold_sheet)
    clear_conditional_formatting(sold_sheet)
    clear_sheet_auto_filter(sold_sheet)

    sold_headers = ensure_sold_sheet_headers(
        sold_sheet,
        source_headers
    )

    for row_data in sold_rows:
        sold_sheet.append([
            row_data.get(header)
            for header in sold_headers
        ])

    sold_last_data_row = sold_sheet.max_row

    format_portfolio_sheet(
        sold_sheet,
        sold_last_data_row,
        sold_headers,
        table_name=SOLD_TABLE_NAME
    )

    return len(sold_rows)


# ==========================================================
# ΕΝΗΜΕΡΩΣΗ portfolio.xlsx
# ==========================================================

def update_portfolio_excel(stocks):
    # ------------------------------------------------------
    # Αν δεν υπάρχει το portfolio.xlsx, δημιουργούμε βάση.
    # ------------------------------------------------------
    if not EXCEL_FILE.exists():
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Portfolio"
        sheet.append(CORE_HEADERS)
        workbook.save(EXCEL_FILE)
        workbook.close()

    # ------------------------------------------------------
    # Ανοίγουμε το υπάρχον portfolio.xlsx.
    # ------------------------------------------------------
    workbook = load_workbook(EXCEL_FILE)
    sheet = workbook.worksheets[0]

    old_headers = get_header_lookup(sheet)

    # ------------------------------------------------------
    # ΠΡΙΝ ΣΒΗΣΟΥΜΕ / ΞΑΝΑΓΡΑΨΟΥΜΕ ΤΟ Portfolio:
    # όποια παλιά θέση δεν υπάρχει πλέον στα νέα stocks
    # μεταφέρεται αυτούσια στο δεύτερο φύλλο "Sold".
    # ------------------------------------------------------
    archive_sold_positions(
        workbook,
        sheet,
        stocks
    )

    # ------------------------------------------------------
    # ΚΡΑΤΑΜΕ MANUAL sector / country με κλειδί
    # (symbol, platform).
    # ------------------------------------------------------
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
                str(symbol).strip().upper(),
                str(platform or "").strip().upper()
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

            manual_data[key] = {
                "sector": sector,
                "country": country,
            }

    # ------------------------------------------------------
    # Αποφασίζουμε ποιες στήλες θα έχει το νέο Excel.
    # Το τωρινό A:O παραμένει A:O αν δεν υπάρχουν metrics.
    # ------------------------------------------------------
    active_headers = get_active_headers(
        stocks=stocks,
        sheet=sheet
    )

    # ------------------------------------------------------
    # Καθαρίζουμε παλιό Excel structure / filters / boxes.
    # ------------------------------------------------------
    remove_existing_tables(sheet)
    remove_existing_merges(sheet)
    clear_conditional_formatting(sheet)
    clear_sheet_auto_filter(sheet)

    if sheet.max_row > 1:
        sheet.delete_rows(
            2,
            sheet.max_row - 1
        )

    remove_extra_columns(
        sheet,
        active_headers
    )

    write_correct_headers(
        sheet,
        active_headers
    )

    # ------------------------------------------------------
    # Ξαναγράφουμε τις τωρινές θέσεις.
    # ------------------------------------------------------
    for stock in stocks:
        symbol = stock.get("symbol")
        platform = stock.get("platform")

        if not symbol:
            continue

        key = (
            str(symbol).strip().upper(),
            str(platform or "").strip().upper()
        )

        old_manual_data = manual_data.get(
            key,
            {}
        )

        # ΠΡΟΤΕΡΑΙΟΤΗΤΑ στα χειροκίνητα sector/country.
        # Αν δεν υπάρχει χειροκίνητη τιμή, χρησιμοποιούμε
        # τυχόν μη κενή τιμή που έρχεται από το stock.
        sector = old_manual_data.get("sector")
        country = old_manual_data.get("country")

        if sector in (None, ""):
            sector = stock.get("sector")

        if country in (None, ""):
            country = stock.get("country")

        sheet.append(
            stock_to_excel_row(
                stock,
                active_headers,
                sector=sector,
                country=country
            )
        )

    last_data_row = sheet.max_row

    # ------------------------------------------------------
    # ΜΟΡΦΟΠΟΙΗΣΗ + TABLE + CONDITIONAL FORMATTING
    # ------------------------------------------------------
    format_portfolio_sheet(
        sheet,
        last_data_row,
        active_headers
    )

    # ------------------------------------------------------
    # 4 SUMMARY BOXES ΚΑΤΩ ΑΠΟ ΤΟΝ ΠΙΝΑΚΑ
    # ------------------------------------------------------
    create_summary_boxes(
        sheet,
        last_data_row
    )

    set_excel_recalculation(workbook)

    workbook.save(EXCEL_FILE)
    workbook.close()

    return EXCEL_FILE
