from pathlib import Path
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.properties import CalcProperties


BASE_DIR = Path(__file__).resolve().parents[2]
EXCEL_FILE = BASE_DIR / "portfolio.xlsx"
OUTPUT_FILE = BASE_DIR / "portfolio_updated.xlsx"

SOLD_SHEET_NAME = "Sold"
SOLD_TABLE_NAME = "SoldSummary"

# Compact view requested for the Sold sheet. These correspond to
# original Portfolio fields A, C, E, F, G, H, I, K plus a monetary
# profit/loss column for each archived sold position.
SOLD_VIEW_HEADERS = [
    "symbol",
    "sector",
    "platform",
    "purchase_date",
    "purchase_price",
    "quantity",
    "current_price",
    "percent_change",
    "total_profit_loss",
]

CANDIDATES_SHEET_NAME = "Candidates"
CANDIDATES_TABLE_NAME = "CandidateResearch"

CANDIDATE_HEADERS = [
    "rank",
    "symbol",
    "name",
    "sector",
    "country",
    "currency",
    "current_price",
    "high_52w",
    "price_25pct_below_high",
    "drop_from_52w_high_amount",
    "discount_from_52w_high_pct",
    "meets_25pct_discount",
    "already_in_portfolio",
    "fcf_yield",
    "fcf_growth",
    "roic",
    "forward_revenue_growth",
    "forward_eps_growth",
    "final_score",
    "market_cap",
    "validation_status",
    "validation_source",
    "researched_at",
    "source_url",
    "dashboard_analysis",
]

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
    "forward_revenue_growth",
    "forward_eps_growth",
    "final_score",
]

# Παραμένει διαθέσιμο για συμβατότητα με τυχόν imports από άλλο module.
HEADERS = CORE_HEADERS + OPTIONAL_HEADERS

# Columns the user wants available in the workbook but hidden
# from the normal Portfolio/Sold view. We address them by name
# rather than by letter so the layout stays correct even after
# deprecated Relative/Absolute columns are removed.
PORTFOLIO_HIDDEN_FIELDS = (
    "sector",
    "purchase_price",
    # V18: quantity must remain visible in the active Portfolio sheet.
    "current_price",
    "market_value",
    "fcf_yield",
    "fcf_growth",
    "roic",
    "forward_revenue_growth",
    "forward_eps_growth",
)


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
    """
    Ζητά από το Excel να επανυπολογίσει τους τύπους στο άνοιγμα.

    Ορισμένα xlsx (π.χ. αρχεία που έχουν ξαναγραφτεί από άλλα εργαλεία)
    δεν περιέχουν calcPr, οπότε το openpyxl φορτώνει
    workbook.calculation = None. Σε αυτή την περίπτωση δημιουργούμε
    ασφαλώς νέο CalcProperties αντί να πετάμε AttributeError.
    """
    if getattr(workbook, "calculation", None) is None:
        workbook.calculation = CalcProperties(
            calcMode="auto",
            fullCalcOnLoad=True,
            forceFullCalc=True,
        )
        return

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
    """
    Χρωματίζει ΟΛΟΚΛΗΡΗ τη γραμμή της θέσης με βάση το
    avg_monthly_change (στήλη M στο τρέχον layout).

    Το monthly_percent_change είναι η απόδοση του τελευταίου μήνα και
    μπορεί να είναι αρνητικό ακόμη κι όταν η θέση είναι συνολικά ανοδική.
    Για το χρώμα χρησιμοποιούμε τον μέσο μηνιαίο ρυθμό απόδοσης:

        avg_monthly_change = total percent_change / μήνες κατοχής

    Δεν χρησιμοποιούμε conditional formatting. Γράφουμε πραγματικό fill
    στα κελιά, ώστε τα χρώματα να φαίνονται πάντα στο Excel και να μπορεί
    να χρησιμοποιηθεί Filter by Color.

    Κατηγορίες:
      > 10%       σκούρο μπλε
      5%..10%     μεσαίο μπλε
      0%..<5%     ανοιχτό μπλε
      -10%..<0%   ανοιχτό πορτοκαλί
      <= -10%     πορτοκαλί
    """
    if last_data_row < 2:
        return

    headers = get_header_lookup(sheet)
    avg_monthly_column = headers.get(
        "avg_monthly_change"
    )

    if avg_monthly_column is None:
        return

    last_column = max(
        1,
        len(active_headers),
    )

    fills = {
        "dark_blue": PatternFill(fill_type="solid", fgColor="1F4E78"),
        "medium_blue": PatternFill(fill_type="solid", fgColor="5B9BD5"),
        "light_blue": PatternFill(fill_type="solid", fgColor="D9EAF7"),
        "light_orange": PatternFill(fill_type="solid", fgColor="FCE4D6"),
        "orange": PatternFill(fill_type="solid", fgColor="ED7D31"),
    }
    no_fill = PatternFill(fill_type=None)

    for row_number in range(2, last_data_row + 1):
        avg_monthly_cell = sheet.cell(
            row=row_number,
            column=avg_monthly_column,
        )

        try:
            value = float(avg_monthly_cell.value)
        except (TypeError, ValueError):
            for column in range(1, last_column + 1):
                cell = sheet.cell(row=row_number, column=column)
                cell.fill = no_fill
                cell.font = Font(color="000000")
            continue

        if value > 10:
            fill = fills["dark_blue"]
            font = Font(color="FFFFFF", bold=True)
        elif value >= 5:
            fill = fills["medium_blue"]
            font = Font(color="FFFFFF", bold=True)
        elif value >= 0:
            fill = fills["light_blue"]
            font = Font(color="000000")
        elif value > -10:
            fill = fills["light_orange"]
            font = Font(color="9C5700")
        else:
            fill = fills["orange"]
            font = Font(color="FFFFFF", bold=True)

        for column in range(1, last_column + 1):
            cell = sheet.cell(
                row=row_number,
                column=column,
            )
            cell.fill = fill
            cell.font = font


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
        "forward_revenue_growth",
        "forward_eps_growth",
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

    for score_field in [
        "final_score",
    ]:
        if score_field not in headers:
            continue

        column = headers[score_field]

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
        "forward_revenue_growth",
        "forward_eps_growth",
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
        "forward_revenue_growth": 24,
        "forward_eps_growth": 21,
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

    # V18: quantity was hidden by V17. Explicitly unhide it so an
    # existing workbook also gets the column back after the next update.
    quantity_column = headers.get("quantity")
    if quantity_column is not None:
        sheet.column_dimensions[
            get_column_letter(quantity_column)
        ].hidden = False

    # User-facing compact view: keep these data fields in the workbook
    # but hide their columns. Deprecated Relative/Absolute columns are
    # not part of active_headers at all and are therefore removed.
    for field in PORTFOLIO_HIDDEN_FIELDS:
        column = headers.get(field)
        if column is None:
            continue

        sheet.column_dimensions[
            get_column_letter(column)
        ].hidden = True

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

    # V18: the total boxes sit three rows below the existing value row,
    # leaving two blank spacer rows between the two summary groups.
    total_title_row = value_row + 3
    total_value_row = total_title_row + 1

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

    # TOTAL PORTFOLIO RETURN: E:F
    sheet.merge_cells(
        start_row=total_title_row,
        start_column=5,
        end_row=total_title_row,
        end_column=6
    )
    sheet.merge_cells(
        start_row=total_value_row,
        start_column=5,
        end_row=total_value_row,
        end_column=6
    )

    # VUAA RETURN: N:O
    # Οι I:J είναι κρυφές στήλες δεδομένων, άρα το summary box
    # μεταφέρεται σε ορατές στήλες.
    sheet.merge_cells(
        start_row=title_row,
        start_column=14,
        end_row=title_row,
        end_column=15
    )
    sheet.merge_cells(
        start_row=value_row,
        start_column=14,
        end_row=value_row,
        end_column=15
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
        row=total_title_row,
        column=2
    ).value = "TOTAL VALUE"

    sheet.cell(
        row=total_title_row,
        column=5
    ).value = "TOTAL PORTFOLIO RETURN"

    sheet.cell(
        row=title_row,
        column=14
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
    # V18 TOTAL VALUE
    # Active Portfolio Value + broker-realized P/L from Sold.
    # If Sold/SoldSummary does not exist yet, keep Portfolio Value.
    # ------------------------------------------------------
    sheet.cell(
        row=total_value_row,
        column=2
    ).value = (
        f'=IFERROR(B{value_row}+SUM(SoldSummary[total_profit_loss]),'
        f'B{value_row})'
    )

    # ------------------------------------------------------
    # V18 TOTAL PORTFOLIO RETURN
    # (TOTAL VALUE - existing active-position cost) / same cost.
    # The cost denominator is exactly the one already used by
    # PORTFOLIO RETURN, so the only new component is realized P/L.
    # ------------------------------------------------------
    active_cost_formula = (
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
    )

    sheet.cell(
        row=total_value_row,
        column=5
    ).value = (
        f'=IFERROR((B{total_value_row}-({active_cost_formula}))'
        f'/({active_cost_formula}),0)'
    )

    # ------------------------------------------------------
    # 3. VUAA RETURN
    # Σταθμισμένος μέσος με portfolio_weight.
    # Τα vuaa_return/portfolio_weight είναι σε μονάδες %, γι' αυτό /100.
    # ------------------------------------------------------
    sheet.cell(
        row=value_row,
        column=14
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
        f"=E{value_row}-N{value_row}"
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
    light_green_fill = PatternFill(
        fill_type="solid",
        fgColor="E2F0D9"
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
    # V18 TOTAL VALUE - B (light green)
    # ------------------------------------------------------
    for row in [total_title_row, total_value_row]:
        cell = sheet.cell(row=row, column=2)
        cell.fill = light_green_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )
        cell.font = Font(bold=False, color="000000")

    sheet.cell(
        row=total_title_row,
        column=2
    ).border = title_border
    sheet.cell(
        row=total_value_row,
        column=2
    ).border = value_border
    sheet.cell(
        row=total_value_row,
        column=2
    ).number_format = '#,##0.00 "€"'

    # ------------------------------------------------------
    # V18 TOTAL PORTFOLIO RETURN - E:F (light green)
    # ------------------------------------------------------
    for row in [total_title_row, total_value_row]:
        for column in range(5, 7):
            cell = sheet.cell(row=row, column=column)
            cell.fill = light_green_fill
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )
            cell.font = Font(bold=False, color="000000")

    sheet.cell(
        row=total_title_row,
        column=5
    ).border = Border(top=medium_black)
    sheet.cell(
        row=total_value_row,
        column=5
    ).number_format = "0.00%"

    # ------------------------------------------------------
    # VUAA RETURN - N:O (ορατό)
    # ------------------------------------------------------
    for row in [title_row, value_row]:
        for column in range(14, 16):
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
        column=14
    ).border = Border(
        top=medium_black
    )

    sheet.cell(
        row=value_row,
        column=14
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
    sheet.row_dimensions[total_title_row].height = 21
    sheet.row_dimensions[total_value_row].height = 21


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
        "forward_revenue_growth": stock.get(
            "forward_revenue_growth"
        ),
        "forward_eps_growth": stock.get(
            "forward_eps_growth"
        ),
        "final_score": stock.get("final_score"),
    }

    return [
        values.get(header)
        for header in active_headers
    ]


# ==========================================================
# ΔΗΜΙΟΥΡΓΙΑ portfolio_updated.xlsx
# ==========================================================

def create_portfolio_excel(stocks, sold_realized_lookup=None):
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

    # ------------------------------------------------------
    # SOLD: compact view + broker-history realized P/L
    # ------------------------------------------------------
    compact_sold_sheet(
        workbook,
        current_stocks=stocks,
        sold_realized_lookup=sold_realized_lookup,
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


def _sold_lookup_key(symbol, platform):
    return (
        str(symbol or "").strip().upper(),
        str(platform or "").strip().upper(),
    )


def _sold_verified_info(row_data, sold_realized_lookup=None):
    if not sold_realized_lookup:
        return {}

    return sold_realized_lookup.get(
        _sold_lookup_key(
            row_data.get("symbol"),
            row_data.get("platform"),
        ),
        {},
    ) or {}


def _sold_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sale_matches_current_position(current_row, verified):
    """
    True when broker history proves a sale belongs to the currently-held
    position. This lets partial sales (for example CRDO) appear in Sold while
    the remaining quantity stays in Portfolio, without importing unrelated
    old sales from years before the current position was opened.
    """
    sold_quantity = _sold_float(verified.get("sold_quantity"))
    if sold_quantity is None or sold_quantity <= 0:
        return False

    purchase_date = normalize_excel_date(current_row.get("purchase_date"))
    sale_date = normalize_excel_date(verified.get("last_sale_date"))

    if isinstance(purchase_date, datetime) and isinstance(sale_date, datetime):
        return sale_date >= purchase_date

    # If one side has no usable date, the broker-reported sold quantity is
    # still stronger evidence than trying to infer a sale from price changes.
    return True


def build_sold_display_rows(
    existing_sold_rows,
    current_stocks=None,
    sold_realized_lookup=None,
):
    """
    Build one Sold row per (symbol, platform).

    Existing fully-sold rows remain. In addition, a currently-held position is
    added when broker history reports a real sold quantity after its purchase
    date. Therefore a partial sale is visible in BOTH sheets:
      * Portfolio -> remaining quantity
      * Sold      -> broker-reported sold quantity

    Broker history is authoritative for sold quantity, executed sale price and
    realised P/L. We do not synthesize unrelated historical broker sales that
    have no matching current or already-archived position.
    """
    sold_realized_lookup = sold_realized_lookup or {}
    current_stocks = current_stocks or []

    existing_by_key = {}
    order = []

    for row in existing_sold_rows or []:
        key = _sold_lookup_key(row.get("symbol"), row.get("platform"))
        if not key[0]:
            continue
        if key not in existing_by_key:
            order.append(key)
        existing_by_key[key] = dict(row)

    current_by_key = {}
    for stock in current_stocks:
        key = _sold_lookup_key(stock.get("symbol"), stock.get("platform"))
        if not key[0]:
            continue
        current_by_key[key] = dict(stock)

    # Add only verified partial sales tied to a current position.
    for key, current_row in current_by_key.items():
        verified = sold_realized_lookup.get(key) or {}
        if key not in existing_by_key and _sale_matches_current_position(
            current_row,
            verified,
        ):
            existing_by_key[key] = dict(current_row)
            order.append(key)

    display_rows = []

    for key in order:
        base = dict(existing_by_key.get(key) or {})
        verified = sold_realized_lookup.get(key) or {}

        sold_quantity = _sold_float(verified.get("sold_quantity"))
        quantity = (
            sold_quantity
            if sold_quantity is not None and sold_quantity > 0
            else _sold_float(base.get("quantity"))
        )

        # For current_price in Sold we want the actual executed sale price in
        # EUR (gross execution price), not a stale market snapshot. If a broker
        # cannot provide it (e.g. Capital transaction rows), keep the archived
        # price rather than inventing one.
        sale_price = _sold_float(verified.get("average_execution_price_eur"))
        if sale_price is None:
            sale_price = _sold_float(verified.get("average_sale_price_eur"))
        if sale_price is None:
            sale_price = _sold_float(base.get("current_price"))

        purchase_price = _sold_float(base.get("purchase_price"))

        percent_change = None
        if (
            purchase_price is not None
            and purchase_price != 0
            and sale_price is not None
        ):
            percent_change = round(
                (sale_price - purchase_price) / purchase_price * 100,
                2,
            )
        elif verified.get("realized_return_pct") is not None:
            percent_change = verified.get("realized_return_pct")
        else:
            percent_change = base.get("percent_change")

        display_rows.append({
            "symbol": base.get("symbol") or verified.get("symbol") or key[0],
            "sector": base.get("sector"),
            "platform": base.get("platform") or verified.get("platform") or key[1],
            "purchase_date": base.get("purchase_date"),
            "purchase_price": purchase_price,
            "quantity": quantity,
            "current_price": sale_price,
            "percent_change": percent_change,
            "total_profit_loss": verified.get("net_profit_loss_eur"),
        })

    return display_rows


def create_sold_summary_boxes(
    sold_sheet,
    last_data_row,
    sold_realized_lookup=None,
):
    """
    Four Sold KPIs based directly on the visible Sold rows.

      SOLD VALUE    = Σ(quantity * purchase_price)
      SOLD RETURN   = Σ(quantity * current_price)
      REALIZED P/L  = Σ broker-reported total_profit_loss
      SOLD % RETURN = (SOLD RETURN - SOLD VALUE) / SOLD VALUE

    This matches the row-level arithmetic the user asked to see in Excel while
    keeping broker realised P/L as a separate authoritative control value.
    """
    if last_data_row < 2:
        return

    title_row = last_data_row + 6
    value_row = title_row + 1

    # B:C, E:F, H:I, K:L
    for start_col in (2, 5, 8, 11):
        sold_sheet.merge_cells(
            start_row=title_row,
            start_column=start_col,
            end_row=title_row,
            end_column=start_col + 1,
        )
        sold_sheet.merge_cells(
            start_row=value_row,
            start_column=start_col,
            end_row=value_row,
            end_column=start_col + 1,
        )

    sold_sheet.cell(row=title_row, column=2).value = "SOLD VALUE"
    sold_sheet.cell(row=title_row, column=5).value = "SOLD RETURN"
    sold_sheet.cell(row=title_row, column=8).value = "REALIZED P/L"
    sold_sheet.cell(row=title_row, column=11).value = "SOLD % RETURN"

    sold_sheet.cell(row=value_row, column=2).value = (
        '=IFERROR(SUMPRODUCT(SoldSummary[quantity],SoldSummary[purchase_price]),0)'
    )
    sold_sheet.cell(row=value_row, column=5).value = (
        '=IFERROR(SUMPRODUCT(SoldSummary[quantity],SoldSummary[current_price]),0)'
    )
    sold_sheet.cell(row=value_row, column=8).value = (
        '=IFERROR(SUM(SoldSummary[total_profit_loss]),0)'
    )
    sold_sheet.cell(row=value_row, column=11).value = (
        f'=IFERROR((E{value_row}-B{value_row})/B{value_row},0)'
    )

    yellow_fill = PatternFill(fill_type="solid", fgColor="FFFF00")
    gray_fill = PatternFill(fill_type="solid", fgColor="D9D9D9")
    peach_fill = PatternFill(fill_type="solid", fgColor="FCE4D6")
    blue_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
    green_fill = PatternFill(fill_type="solid", fgColor="E2F0D9")
    red_fill = PatternFill(fill_type="solid", fgColor="FCE4D6")
    medium_black = Side(style="medium", color="000000")

    fills = {
        2: yellow_fill,
        5: gray_fill,
        8: peach_fill,
        11: blue_fill,
    }

    for start_col, fill in fills.items():
        for row in (title_row, value_row):
            for column in range(start_col, start_col + 2):
                cell = sold_sheet.cell(row=row, column=column)
                cell.fill = fill
                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                )
        sold_sheet.cell(row=title_row, column=start_col).border = Border(
            top=medium_black
        )

    sold_sheet.cell(row=value_row, column=2).number_format = '#,##0.00 "€"'
    sold_sheet.cell(row=value_row, column=5).number_format = '#,##0.00 "€"'
    sold_sheet.cell(row=value_row, column=8).number_format = '#,##0.00 "€"'
    sold_sheet.cell(row=value_row, column=11).number_format = "0.00%"

    # Dynamic green/red highlighting for realised P/L and percentage return.
    sold_sheet.conditional_formatting.add(
        f"H{value_row}:I{value_row}",
        FormulaRule(
            formula=[f"$H${value_row}>=0"],
            fill=green_fill,
        ),
    )
    sold_sheet.conditional_formatting.add(
        f"H{value_row}:I{value_row}",
        FormulaRule(
            formula=[f"$H${value_row}<0"],
            fill=red_fill,
        ),
    )
    sold_sheet.conditional_formatting.add(
        f"K{value_row}:L{value_row}",
        FormulaRule(
            formula=[f"$K${value_row}>=0"],
            fill=green_fill,
        ),
    )
    sold_sheet.conditional_formatting.add(
        f"K{value_row}:L{value_row}",
        FormulaRule(
            formula=[f"$K${value_row}<0"],
            fill=red_fill,
        ),
    )

    sold_sheet.row_dimensions[title_row].height = 21
    sold_sheet.row_dimensions[value_row].height = 21


def compact_sold_sheet(
    workbook,
    current_stocks=None,
    sold_realized_lookup=None,
):
    """
    Rebuild the compact Sold view.

    The function now also creates Sold when the only sale is partial. Quantity
    is always visible. Trading212/Freedom current_price is the executed sale
    price in EUR when broker history supplies it.
    """
    current_stocks = current_stocks or []
    sold_realized_lookup = sold_realized_lookup or {}

    existing_rows = []
    if SOLD_SHEET_NAME in workbook.sheetnames:
        sold_sheet = workbook[SOLD_SHEET_NAME]
        existing_rows, _ = collect_portfolio_rows(sold_sheet)
    else:
        # A new Sold sheet is needed only when there is at least one current
        # position with a verified partial sale.
        has_partial = any(
            _sale_matches_current_position(
                stock,
                sold_realized_lookup.get(
                    _sold_lookup_key(stock.get("symbol"), stock.get("platform")),
                    {},
                ) or {},
            )
            for stock in current_stocks
            if stock.get("symbol")
        )
        if not has_partial:
            return
        sold_sheet = workbook.create_sheet(
            title=SOLD_SHEET_NAME,
            index=1,
        )

    display_rows = build_sold_display_rows(
        existing_rows,
        current_stocks=current_stocks,
        sold_realized_lookup=sold_realized_lookup,
    )

    remove_existing_tables(sold_sheet)
    remove_existing_merges(sold_sheet)
    clear_conditional_formatting(sold_sheet)
    clear_sheet_auto_filter(sold_sheet)

    if sold_sheet.max_row > 0:
        sold_sheet.delete_rows(1, sold_sheet.max_row)

    if sold_sheet.max_column > len(SOLD_VIEW_HEADERS):
        sold_sheet.delete_cols(
            len(SOLD_VIEW_HEADERS) + 1,
            sold_sheet.max_column - len(SOLD_VIEW_HEADERS),
        )

    sold_sheet.append(SOLD_VIEW_HEADERS)

    for row_data in display_rows:
        sold_sheet.append([
            row_data.get(header)
            for header in SOLD_VIEW_HEADERS
        ])

    last_row = sold_sheet.max_row

    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in sold_sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    sold_sheet.freeze_panes = "A2"
    sold_sheet.sheet_view.showGridLines = False

    widths = {
        "A": 14,
        "B": 20,
        "C": 14,
        "D": 14,
        "E": 14,
        "F": 12,
        "G": 14,
        "H": 15,
        "I": 18,
    }

    # Old formatting could leave quantity/current_price hidden. The compact
    # Sold sheet must always expose all nine requested columns, especially F.
    for column_letter, width in widths.items():
        sold_sheet.column_dimensions[column_letter].width = width
        sold_sheet.column_dimensions[column_letter].hidden = False

    positive_fill = PatternFill(fill_type="solid", fgColor="E2F0D9")
    negative_fill = PatternFill(fill_type="solid", fgColor="FCE4D6")

    for row_number in range(2, last_row + 1):
        sold_sheet.cell(row=row_number, column=4).number_format = "dd/mm/yyyy"

        for column in (5, 7, 9):
            sold_sheet.cell(
                row=row_number,
                column=column,
            ).number_format = '#,##0.00 "€"'

        sold_sheet.cell(
            row=row_number,
            column=6,
        ).number_format = "0.########"

        sold_sheet.cell(
            row=row_number,
            column=8,
        ).number_format = '0.00"%"'

        pnl_cell = sold_sheet.cell(row=row_number, column=9)

        if isinstance(pnl_cell.value, (int, float)):
            if pnl_cell.value >= 0:
                pnl_cell.fill = positive_fill
                pnl_cell.font = Font(bold=True, color="375623")
            else:
                pnl_cell.fill = negative_fill
                pnl_cell.font = Font(bold=True, color="9C5700")

    if last_row >= 2:
        table = Table(
            displayName=SOLD_TABLE_NAME,
            ref=f"A1:I{last_row}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sold_sheet.add_table(table)

        create_sold_summary_boxes(
            sold_sheet,
            last_row,
            sold_realized_lookup=sold_realized_lookup,
        )


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

def update_portfolio_excel(stocks, sold_realized_lookup=None):
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
    # ΜΟΡΦΟΠΟΙΗΣΗ + TABLE + ROW COLORS
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

    # ------------------------------------------------------
    # SOLD: κάθε update ξαναγράφει το compact Sold view και
    # περνά verified broker-history realized P/L.
    # ------------------------------------------------------
    compact_sold_sheet(
        workbook,
        current_stocks=stocks,
        sold_realized_lookup=sold_realized_lookup,
    )

    set_excel_recalculation(workbook)

    workbook.save(EXCEL_FILE)
    workbook.close()

    return EXCEL_FILE

# ==========================================================
# CANDIDATE RESEARCH SHEET
# ==========================================================

def update_candidate_research_excel(
    candidates,
    research_meta=None,
):
    """
    Γράφει / ανανεώνει το φύλλο Candidates στο portfolio.xlsx.

    Το Portfolio και το Sold δεν πειράζονται.
    Κάθε νέα έρευνα αντικαθιστά μόνο το προηγούμενο Candidates.
    """
    if not EXCEL_FILE.exists():
        workbook = Workbook()
        portfolio_sheet = workbook.active
        portfolio_sheet.title = "Portfolio"
        portfolio_sheet.append(CORE_HEADERS)
        workbook.save(EXCEL_FILE)
        workbook.close()

    workbook = load_workbook(EXCEL_FILE)

    if CANDIDATES_SHEET_NAME in workbook.sheetnames:
        old_sheet = workbook[
            CANDIDATES_SHEET_NAME
        ]
        workbook.remove(old_sheet)

    # Αν υπάρχει Sold, το Candidates γίνεται 3ο φύλλο.
    # Διαφορετικά γίνεται 2ο.
    insert_index = (
        2
        if SOLD_SHEET_NAME in workbook.sheetnames
        else 1
    )

    sheet = workbook.create_sheet(
        title=CANDIDATES_SHEET_NAME,
        index=insert_index,
    )

    sheet.append(CANDIDATE_HEADERS)

    for candidate in candidates or []:
        sheet.append([
            candidate.get(header)
            for header in CANDIDATE_HEADERS
        ])

    last_data_row = sheet.max_row
    last_column = len(CANDIDATE_HEADERS)
    last_column_letter = get_column_letter(
        last_column
    )

    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="1F4E78",
    )
    header_font = Font(
        bold=True,
        color="FFFFFF",
    )

    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    sheet.row_dimensions[1].height = 36

    headers = get_header_lookup(sheet)

    # ------------------------------
    # Numeric formats
    # ------------------------------
    price_fields = [
        "current_price",
        "high_52w",
        "price_25pct_below_high",
        "drop_from_52w_high_amount",
    ]

    percent_fields = [
        "discount_from_52w_high_pct",
        "fcf_yield",
        "fcf_growth",
        "roic",
        "forward_revenue_growth",
        "forward_eps_growth",
    ]

    score_fields = [
        "final_score",
    ]

    for field in price_fields:
        column = headers.get(field)
        if column is None:
            continue

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column,
            ).number_format = "#,##0.00"

    for field in percent_fields:
        column = headers.get(field)
        if column is None:
            continue

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column,
            ).number_format = '0.00"%"'

    for field in score_fields:
        column = headers.get(field)
        if column is None:
            continue

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column,
            ).number_format = "0.00"

    market_cap_col = headers.get(
        "market_cap"
    )
    if market_cap_col is not None:
        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=market_cap_col,
            ).number_format = "#,##0"

    # ------------------------------
    # Source hyperlinks
    # ------------------------------
    source_col = headers.get(
        "source_url"
    )
    if source_col is not None:
        for row in range(2, last_data_row + 1):
            cell = sheet.cell(
                row=row,
                column=source_col,
            )
            if cell.value:
                cell.hyperlink = str(
                    cell.value
                )
                cell.style = "Hyperlink"

    # ------------------------------
    # Alignment
    # ------------------------------
    for row in range(2, last_data_row + 1):
        for column in range(1, last_column + 1):
            sheet.cell(
                row=row,
                column=column,
            ).alignment = Alignment(
                vertical="center"
            )

    center_fields = [
        "rank",
        "symbol",
        "sector",
        "country",
        "currency",
        "meets_25pct_discount",
        "already_in_portfolio",
        "validation_status",
        "researched_at",
    ]

    for field in center_fields:
        column = headers.get(field)
        if column is None:
            continue

        for row in range(2, last_data_row + 1):
            sheet.cell(
                row=row,
                column=column,
            ).alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

    # ------------------------------
    # Conditional formatting
    # ------------------------------
    final_col = headers.get(
        "final_score"
    )
    if final_col is not None and last_data_row >= 2:
        final_letter = get_column_letter(
            final_col
        )
        sheet.conditional_formatting.add(
            f"{final_letter}2:{final_letter}{last_data_row}",
            FormulaRule(
                formula=[
                    f"${final_letter}2>=70"
                ],
                fill=PatternFill(
                    fill_type="solid",
                    fgColor="C6E0B4",
                ),
            ),
        )
        sheet.conditional_formatting.add(
            f"{final_letter}2:{final_letter}{last_data_row}",
            FormulaRule(
                formula=[
                    f"${final_letter}2<40"
                ],
                fill=PatternFill(
                    fill_type="solid",
                    fgColor="F4CCCC",
                ),
            ),
        )

    discount_col = headers.get(
        "discount_from_52w_high_pct"
    )
    if discount_col is not None and last_data_row >= 2:
        discount_letter = get_column_letter(
            discount_col
        )
        sheet.conditional_formatting.add(
            f"{discount_letter}2:{discount_letter}{last_data_row}",
            FormulaRule(
                formula=[
                    f"${discount_letter}2>=25"
                ],
                fill=PatternFill(
                    fill_type="solid",
                    fgColor="FFF2CC",
                ),
            ),
        )

    # ------------------------------
    # Widths
    # ------------------------------
    widths = {
        "rank": 8,
        "symbol": 14,
        "name": 34,
        "sector": 22,
        "country": 18,
        "currency": 10,
        "current_price": 14,
        "high_52w": 14,
        "price_25pct_below_high": 23,
        "drop_from_52w_high_amount": 24,
        "discount_from_52w_high_pct": 25,
        "meets_25pct_discount": 22,
        "already_in_portfolio": 20,
        "fcf_yield": 14,
        "fcf_growth": 15,
        "roic": 12,
        "forward_revenue_growth": 24,
        "forward_eps_growth": 21,
        "final_score": 14,
        "market_cap": 18,
        "validation_status": 18,
        "validation_source": 34,
        "researched_at": 21,
        "source_url": 48,
        "dashboard_analysis": 70,
    }

    for field, width in widths.items():
        column = headers.get(field)
        if column is None:
            continue

        sheet.column_dimensions[
            get_column_letter(column)
        ].width = width

    # User-facing Candidates view: only A-E, G, S and X remain visible.
    # Everything else stays in the workbook for calculations/dashboard but
    # is hidden from the normal Excel view.
    candidate_visible_columns = {
        "A", "B", "C", "D", "E", "G", "S", "X"
    }

    for column_number in range(1, last_column + 1):
        column_letter = get_column_letter(column_number)
        sheet.column_dimensions[column_letter].hidden = (
            column_letter not in candidate_visible_columns
        )

    # Excel table only when there is data.
    if last_data_row >= 2:
        table = Table(
            displayName=CANDIDATES_TABLE_NAME,
            ref=(
                f"A1:{last_column_letter}"
                f"{last_data_row}"
            ),
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)

    set_excel_recalculation(workbook)
    workbook.save(EXCEL_FILE)
    workbook.close()

    return EXCEL_FILE
