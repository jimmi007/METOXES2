"""V22: six-month purchase cohorts, measured on three common monthly windows."""
from datetime import date, datetime, timedelta, timezone
from statistics import mean
try:
    from .portfolio_review_service import number, parse_date, months_before, cohort_stats, beta_assessment
except ImportError:
    from portfolio_review_service import number, parse_date, months_before, cohort_stats, beta_assessment


def history_metrics(points, asof):
    """points: date, close (split-adjusted), adjusted_close (total-return proxy)."""
    asof = parse_date(asof)
    points = sorted([p for p in points if parse_date(p.get('date')) and parse_date(p['date']) <= asof], key=lambda p: p['date'])
    anchors = [months_before(asof, n) for n in (3, 2, 1, 0)]
    selected = []
    for anchor in anchors:
        eligible = [p for p in points if timedelta(0) <= anchor-parse_date(p['date']) <= timedelta(days=7)
                    and number(p.get('adjusted_close')) is not None and number(p['adjusted_close']) > 0]
        if not eligible:
            return {'as_of': str(asof), 'status': 'insufficient_history', 'mean_monthly_3m_pct': None,
                    'mean_close_3m': None, 'monthly_returns': []}
        selected.append(eligible[-1])
    returns = [(selected[i+1]['adjusted_close']/selected[i]['adjusted_close']-1)*100 for i in range(3)]
    closes = [number(p.get('close')) for p in points if anchors[0] < parse_date(p['date']) <= asof and number(p.get('close')) is not None]
    return {'as_of': str(asof), 'status': 'available', 'mean_monthly_3m_pct': round(mean(returns), 4),
            'total_3m_pct': round((selected[-1]['adjusted_close']/selected[0]['adjusted_close']-1)*100, 4),
            'mean_close_3m': round(mean(closes), 4) if closes else None,
            'monthly_returns': [round(v, 4) for v in returns], 'price_dates': [p['date'] for p in selected],
            'period_start': str(anchors[0]), 'period_end': str(asof),
            'source': 'Yahoo Finance: adjusted closes for returns; Close for average price'}


def build_six_month_review(stocks, asof, histories):
    asof = parse_date(asof) or date.today()
    cutoff = months_before(asof, 6)
    groups = [[], []]
    excluded = []
    for stock in stocks:
        bought = parse_date(stock.get('purchase_date'))
        if not bought or bought > asof:
            excluded.append(stock.get('symbol')); continue
        hist = histories.get(stock.get('symbol'), {})
        valid = hist.get('as_of') == str(asof) and hist.get('status') == 'available'
        row = {k: stock.get(k) for k in ('symbol','name','platform','purchase_date','purchase_price','current_price','quantity','percent_change','currency')}
        row['currency'] = hist.get('currency') or stock.get('currency')
        row['history'] = hist if valid else {'status': 'missing_or_stale'}
        row['monthly_percent_change'] = number(hist.get('mean_monthly_3m_pct')) if valid else None
        row['includes_pre_purchase'] = bought > months_before(asof, 3)
        groups[0 if bought >= cutoff else 1].append(row)
    a, b = [cohort_stats(g) for g in groups]
    delta = a['mean_monthly_pct']-b['mean_monthly_pct'] if a['mean_monthly_pct'] is not None and b['mean_monthly_pct'] is not None else None
    return {'as_of': str(asof), 'cutoff': str(cutoff), 'performance_start': str(months_before(asof, 3)),
            'recent': a, 'older': b, 'difference_pp': round(delta,4) if delta is not None else None,
            'rows': groups[0], 'older_rows': groups[1], 'excluded_date_symbols': excluded,
            'method': 'Αγορές τελευταίων 6 ημερολογιακών μηνών έναντι παλαιότερων. Επίδοση: αριθμητικός μέσος των 3 μηνιαίων μεταβολών στις ίδιες κυλιόμενες περιόδους για όλους. Ένα ticker ανά ομάδα, ανεξάρτητα από broker. Κλεισίματα στην ημερομηνία αναφοράς ή στην προηγούμενη συνεδρίαση (έως 7 ημέρες). Αποδόσεις από προσαρμοσμένες τιμές Yahoo (splits/μερίσματα). Η μέση τιμή κλεισίματος 3Μ εμφανίζεται χωριστά ανά μετοχή και νόμισμα· δεν αθροίζεται μεταξύ εταιρειών. Ελλιπές ή παλιό ιστορικό εξαιρείται. Η μέτρηση μπορεί να περιέχει ημέρες πριν από την αγορά.'}


def attach_extended(payload, cache, snapshot):
    asof = parse_date(payload['generated_at']) or date.today()
    payload['six_month_review'] = build_six_month_review(payload['stocks'], asof, cache.get('history_3m', {}))
    source = snapshot.get('us_list', {})
    checked = parse_date(source.get('checked_at'))
    status = 'available' if checked and 0 <= (asof-checked).days <= 7 else 'stale' if checked else 'not_synced'
    candidate_map = {r.get('symbol'): r for r in payload['candidates']}
    rows = []
    for item in source.get('rows', []):
        row = dict(item)
        data = cache.get('investing_quotes', {}).get(item.get('source_url'), {})
        row.update(data)
        bd = parse_date(row.get('beta_checked_at'))
        row['quote_status'] = 'available' if bd and 0 <= (asof-bd).days <= 7 else 'stale' if bd else 'missing'
        row['beta_assessment'] = beta_assessment(row.get('beta'))
        row['final_score'] = candidate_map.get(row.get('symbol'), {}).get('final_score')
        row['score_source'] = 'Project candidate score' if row['final_score'] is not None else 'Δεν έχει υπολογιστεί score στο project'
        low, price = number(row.get('low_52w')), number(row.get('current_price'))
        row['distance_from_52w_low_pct'] = round((price/low-1)*100, 2) if low and low > 0 and price is not None else None
        rows.append(row)
    payload['investing_us'] = {'rows': rows, 'status': status, 'checked_at': source.get('checked_at'),
        'source_url': 'https://gr.investing.com/equities/united-states/most-undervalued',
        'last_attempt': snapshot.get('us_last_attempt'),
        'scope': 'Η εμφανιζόμενη λίστα Investing Most Undervalued ΗΠΑ. Η σειρά διατηρείται όπως στην πηγή. Το upside Investing δεν είναι Final Score. Beta/52W από Yahoo μετά από μοναδική αντιστοίχιση εταιρείας σε αμερικανικό χρηματιστήριο.'}
    return payload
