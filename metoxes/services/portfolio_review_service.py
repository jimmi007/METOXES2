"""V21: auditable cohorts and time-bounded enrichment. No credentials in output."""
from __future__ import annotations
import calendar, json, math, os, re, signal, subprocess, sys, tempfile, time
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]

def number(v):
    try:
        n=float(v) if not isinstance(v, bool) else float('nan')
        return n if math.isfinite(n) else None
    except (ValueError, TypeError): return None

def parse_date(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    for fmt in ('%Y-%m-%d','%d/%m/%Y'):
        try: return datetime.strptime(str(v)[:10],fmt).date()
        except ValueError: pass
    return None

def months_before(d, n):
    y,m=divmod(d.year*12+d.month-1-n,12)
    return date(y,m+1,min(d.day,calendar.monthrange(y,m+1)[1]))

def load(path):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}

def clean(value):
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items() if not re.search(r'^(api_?key|password|token|authorization)$',k,re.I)}
    if isinstance(value,list): return [clean(x) for x in value]
    if isinstance(value,str):
        return re.sub(r'(?i)([?&](?:apikey|api_key|token|access_token)=)[^&\s\'"<>]+',r'\1[REDACTED]',value)
    return value

def beta_assessment(v):
    b=number(v)
    if b is None: return 'Μη διαθέσιμο beta: δεν εξάγεται συμπέρασμα για την ευαισθησία στην αγορά.'
    label=('αρνητική ιστορική συσχέτιση' if b<0 else 'χαμηλότερη ευαισθησία' if b<0.8 else 'παρόμοια ευαισθησία' if b<=1.2 else 'αυξημένη ευαισθησία' if b<=1.5 else 'πολύ αυξημένη ευαισθησία')
    return (f'Beta {b:.2f}: {label} έναντι του δείκτη αναφοράς του παρόχου. '
            f'Ενδεικτικά, κίνηση του δείκτη +1% αντιστοιχεί στο γραμμικό μοντέλο σε {b:+.2f}% και -1% σε {-b:+.2f}%, με τους άλλους παράγοντες σταθερούς. '
            'Είναι ιστορική εκτίμηση, όχι πρόβλεψη ή συνολικός κίνδυνος. Χαμηλό beta δεν αποκλείει μεγάλη ζημιά, ειδικά σε μικρές ή βιοτεχνολογικές εταιρείες. '
            'Τα beta διαφορετικών αγορών δεν είναι απόλυτα συγκρίσιμα. Δεν αλλάζει το Final Score.')

def cohort_stats(rows):
    # Equal weight per security; broker duplicates are one security in each cohort.
    grouped={}
    for r in rows: grouped.setdefault(str(r.get('symbol')),[]).append(r)
    vals=[]
    for group in grouped.values():
        vs=[number(r.get('monthly_percent_change')) for r in group]
        vs=[v for v in vs if v is not None]
        if vs: vals.append(mean(vs))
    cost=value=0.0
    for r in rows:
        p,q,now=(number(r.get(k)) for k in ('purchase_price','quantity','current_price'))
        if p is not None and q is not None and now is not None and p>0 and q>0:
            cost+=p*q;value+=now*q
    return {'positions':len(rows),'securities':len(grouped),'valid_monthly':len(vals),
            'mean_monthly_pct':round(mean(vals),4) if vals else None,
            'median_monthly_pct':round(median(vals),4) if vals else None,
            'positive_pct':round(100*sum(v>0 for v in vals)/len(vals),2) if vals else None,
            'since_purchase_pct':round((value/cost-1)*100,4) if cost else None}

def holding_period_metrics(row, asof, history=None):
    """Open-position estimate in portfolio EUR basis, limited to owned days.

    Without transactions and historical FX this is not a broker cash ledger.
    Thirty days deliberately matches the project's LastMonth definition.
    """
    asof = parse_date(asof)
    bought = parse_date(row.get('purchase_date'))
    start = max(bought, asof-timedelta(days=30)) if bought and asof else None
    result = {'monthly_profit_loss': None, 'holding_monthly_pct': None,
              'monthly_start_value': None, 'monthly_period_start': str(start) if start else None,
              'monthly_period_end': str(asof) if asof else None,
              'monthly_basis': 'unavailable', 'monthly_estimate': True}
    value = number(row.get('market_value'))
    if not bought or not asof or bought > asof or value is None or value < 0:
        return result
    if bought >= asof-timedelta(days=30):
        price, quantity = number(row.get('purchase_price')), number(row.get('quantity'))
        if price is None or quantity is None or price <= 0 or quantity <= 0:
            return result
        base = price * quantity
        result['monthly_basis'] = 'purchase_cost'
    else:
        hist = history or {}
        valid = hist.get('as_of') == str(asof)
        rate = number(hist.get('last_month_price_pct')) if valid else None
        price_dates=hist.get('last_month_price_dates') or []
        if rate is not None and price_dates:
            dates=[parse_date(d) for d in price_dates]
            anchors=[asof-timedelta(days=30),asof]
            if len(dates)!=2 or any(d is None or not timedelta(0)<=anchor-d<=timedelta(days=7) for d,anchor in zip(dates,anchors)) or dates[0]<bought or dates[1]<dates[0]:
                rate=None
        if rate is not None:
            result['monthly_basis'] = 'historical_close'
            result['monthly_price_dates'] = hist.get('last_month_price_dates', [])
        else:
            rate = number(row.get('monthly_percent_change'))
            result['monthly_basis'] = 'portfolio_1m_fallback'
        if rate is None or rate <= -100:
            result['monthly_basis'] = 'unavailable'
            return result
        base = value / (1+rate/100)
    if base <= 0:
        return result
    result.update(monthly_profit_loss=value-base, monthly_start_value=base,
                  holding_monthly_pct=(value/base-1)*100)
    return result


def holding_group_stats(rows):
    stats = cohort_stats(rows)
    valid = [r for r in rows if number(r.get('monthly_profit_loss')) is not None
             and number(r.get('monthly_start_value')) is not None and r['monthly_start_value'] > 0]
    base = sum(r['monthly_start_value'] for r in valid)
    profit = sum(r['monthly_profit_loss'] for r in valid)
    stats.update(monthly_profit_loss=profit if valid else None,
                 weighted_monthly_pct=profit/base*100 if base else None,
                 monthly_profit_loss_covered=len(valid), monthly_profit_loss_total=len(rows))
    return stats


def purchase_metrics(row, sold=False):
    price, qty = number(row.get('purchase_price')), number(row.get('quantity'))
    cost = price*qty if price is not None and qty is not None and price>0 and qty>0 else None
    value = number(row.get('market_value'))
    profit = number(row.get('total_profit_loss')) if sold else (
        value-cost if value is not None and value>=0 and cost is not None else None)
    return dict(purchase_cost=cost, purchase_profit_loss=profit,
                purchase_return_pct=profit/cost*100 if cost and profit is not None else None)


def acquisition_totals(open_rows, sold_rows):
    groups={}; pairs=[]; open_profits=[]; sold_profits=[]
    for rows, is_sold in ((open_rows, False), (sold_rows, True)):
        for row in rows:
            metrics=purchase_metrics(row,is_sold)
            cost,profit=metrics['purchase_cost'],metrics['purchase_profit_loss']
            key=(str(row.get('symbol','')).upper(),str(row.get('platform','')).strip().lower(),str(parse_date(row.get('purchase_date'))))
            groups.setdefault(key,[]).append(profit)
            if profit is not None:
                (sold_profits if is_sold else open_profits).append(profit)
            if cost is not None and profit is not None:pairs.append((cost,profit))
    wins=sum(all(v is not None for v in values) and sum(values)>0 for values in groups.values())
    unknown=sum(any(v is None for v in values) for values in groups.values())
    base=sum(c for c,p in pairs); gain=sum(p for c,p in pairs)
    profits=open_profits+sold_profits
    count=len(open_rows)+len(sold_rows)
    return {'winning_purchases':wins,'total_purchases':len(groups),'unknown_purchases':unknown,
            'winning_purchase_pct':wins/len(groups)*100 if groups else None,
            'combined_return_pct':gain/base*100 if base else None,
            'combined_profit_loss':sum(profits) if profits or not count else None,
            'combined_covered':len(profits),'combined_positions':count,
            'combined_return_covered':len(pairs),'return_cost':base,'return_profit_loss':gain,
            'open_profit_loss':sum(open_profits) if open_profits or not open_rows else None,
            'sold_profit_loss':sum(sold_profits) if sold_profits or not sold_rows else None}


def row_issues(row, sold=False):
    issues=[]
    if row.get('purchase_cost') is None: issues.append('Λείπει έγκυρη τιμή αγοράς ή ποσότητα')
    if row.get('purchase_profit_loss') is None:
        issues.append('Λείπει πραγματοποιημένο κέρδος/ζημιά πώλησης' if sold else 'Δεν υπολογίζεται αποτέλεσμα από απόκτηση: ελέγξτε κόστος και τρέχουσα αξία')
    if not sold and row.get('monthly_profit_loss') is None: issues.append('Λείπουν στοιχεία για LastMonth')
    if not sold and row.get('monthly_basis')=='portfolio_1m_fallback': issues.append('LastMonth: εκτίμηση από απόδοση 1Μ, χωρίς έγκυρα ιστορικά κλεισίματα')
    if not sold and row.get('monthly_basis')=='historical_close' and not row.get('monthly_price_dates'): issues.append('Λείπουν ημερομηνίες ιστορικών κλεισιμάτων LastMonth')
    if not str(row.get('platform') or '').strip(): issues.append('Λείπει πλατφόρμα')
    return issues


def audit_review(review):
    """Reconcile displayed rows, cash amounts, return bases and ownership periods."""
    errors=[]; issues=list(review.get('excluded_rows',[])); checks=0
    def check(label, actual, expected):
        nonlocal checks
        checks+=1
        a,b=number(actual),number(expected)
        if not ((a is None and b is None) or (a is not None and b is not None and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-7))):
            errors.append(dict(check=label,actual=actual,expected=expected))
    asof=parse_date(review['as_of'])
    for key,op,so in [('recent','rows','sold_rows'),('older','older_rows','older_sold_rows')]:
        opened,sold=review[op],review[so]; group=review[key]
        for rows,is_sold in [(opened,False),(sold,True)]:
            for row in rows:
                label=f"{row.get('symbol')} / {row.get('platform')}"
                for reason in row.get('data_issues',[]):
                    issues.append(dict(symbol=row.get('symbol'),platform=row.get('platform'),reason=reason))
                price,qty=number(row.get('purchase_price')),number(row.get('quantity'))
                cost=price*qty if price is not None and qty is not None and price>0 and qty>0 else None
                value=number(row.get('market_value'))
                expected=number(row.get('total_profit_loss')) if is_sold else (value-cost if value is not None and value>=0 and cost is not None else None)
                check(label+' από απόκτηση',row.get('purchase_profit_loss'),expected)
                check(label+' απόδοση από απόκτηση',row.get('purchase_return_pct'),expected/cost*100 if cost and expected is not None else None)
                if is_sold:
                    check(label+' πραγματοποιημένο',row.get('realized_profit_loss'),expected)
                    if not parse_date(row.get('sell_date')) or not parse_date(row['purchase_date'])<=parse_date(row['sell_date'])<=asof:
                        errors.append(dict(check=label+' ημερομηνία πώλησης',actual=row.get('sell_date'),expected='από αγορά έως αναφορά'))
                else:
                    start=max(parse_date(row['purchase_date']),asof-timedelta(days=30))
                    checks+=1
                    if row.get('monthly_period_start')!=str(start) or row.get('monthly_period_end')!=str(asof):
                        errors.append(dict(check=label+' διάστημα LastMonth',actual=row.get('monthly_period_start'),expected=str(start)))
                    base=number(row.get('monthly_start_value'))
                    expected_month=value-base if value is not None and base is not None and base>0 else None
                    check(label+' LastMonth',row.get('monthly_profit_loss'),expected_month)
                    if base is not None and start==parse_date(row['purchase_date']):check(label+' βάση αγοράς',base,cost)
                    check(label+' απόδοση LastMonth',row.get('holding_monthly_pct'),expected_month/base*100 if base and expected_month is not None else None)
        monthly=[r for r in opened if number(r.get('monthly_profit_loss')) is not None and number(r.get('monthly_start_value')) is not None and r['monthly_start_value']>0]
        month=sum(r['monthly_profit_loss'] for r in monthly) if monthly else None
        base=sum(r['monthly_start_value'] for r in monthly)
        check(key+' σύνολο LastMonth',group['monthly_profit_loss'],month)
        check(key+' απόδοση LastMonth',group['weighted_monthly_pct'],month/base*100 if base else None)
        allprofits=[]
        for field,rows in [('open_profit_loss',opened),('sold_profit_loss',sold)]:
            values=[r['purchase_profit_loss'] for r in rows if r.get('purchase_profit_loss') is not None]
            allprofits.extend(values)
            check(key+' '+field,group[field],sum(values) if values or not rows else None)
        check(key+' σύνολο από απόκτηση',group['combined_profit_loss'],sum(allprofits) if allprofits or not opened+sold else None)
        pairs=[(r['purchase_cost'],r['purchase_profit_loss']) for r in opened+sold if r.get('purchase_cost') and r.get('purchase_profit_loss') is not None]
        cost=sum(c for c,v in pairs)
        check(key+' Total return from PD',group['combined_return_pct'],sum(v for c,v in pairs)/cost*100 if cost else None)
        check(key+' κάλυψη ποσών',group['combined_covered'],len(allprofits))
        check(key+' κάλυψη απόδοσης',group['combined_return_covered'],len(pairs))
    return dict(status='error' if errors else 'partial' if issues else 'ok',checks=checks,errors=errors,issues=issues)


def build_review(stocks, asof, news=None, histories=None, sold_stocks=None, _platform_views=True):
    asof=parse_date(asof) or date.today(); cutoff=months_before(asof,3)
    new=[];old=[];excluded=[];excluded_rows=[]
    for original in stocks:
        d=parse_date(original.get('purchase_date'))
        if not d or d>asof:
            excluded.append(original.get('symbol'))
            excluded_rows.append(dict(symbol=original.get('symbol'),platform=original.get('platform'),reason='Ανοικτή θέση: λείπει έγκυρη ημερομηνία απόκτησης έως την αναφορά'))
            continue
        r=dict(original)
        r.update(purchase_metrics(r))
        r.update(holding_period_metrics(r, asof, (histories or {}).get(r.get('symbol'))))
        # Monthly average since acquisition, same simple definition as Excel.
        elapsed=max(1,(asof.year-d.year)*12+asof.month-d.month-(asof.day<d.day))
        total=number(r.get('percent_change'))
        r['avg_monthly_change']=total/elapsed if total is not None else None
        r['news']=(news or {}).get(r.get('symbol'),{})
        r['data_issues']=row_issues(r)
        (new if d>=cutoff else old).append(r)
    sold_groups=[[],[]]; excluded_sold=0
    for source in sold_stocks or []:
        bought, sold = parse_date(source.get('purchase_date')), parse_date(source.get('sell_date'))
        if not bought or not sold or not bought<=sold<=asof:
            excluded_sold+=1
            excluded_rows.append(dict(symbol=source.get('symbol'),platform=source.get('platform'),reason='Sold: λείπουν έγκυρες ημερομηνίες αγοράς/πώλησης ή η πώληση προηγείται της αγοράς/έπεται της αναφοράς'))
            continue
        r=dict(source)
        r.update(purchase_metrics(r,True))
        r['realized_profit_loss']=r['purchase_profit_loss']
        r['realized_return_pct']=r['purchase_return_pct']
        r['data_issues']=row_issues(r,True)
        sold_groups[0 if bought>=cutoff else 1].append(r)
    a,b=holding_group_stats(new),holding_group_stats(old)
    a.update(acquisition_totals(new,sold_groups[0]));b.update(acquisition_totals(old,sold_groups[1]))
    av,bv=a['weighted_monthly_pct'],b['weighted_monthly_pct']
    delta=av-bv if av is not None and bv is not None else None
    key=lambda x:number(x.get('holding_monthly_pct')) if number(x.get('holding_monthly_pct')) is not None else -1e9
    result = {'as_of':str(asof),'cutoff':str(cutoff),'recent':a,'older':b,'excluded_rows':excluded_rows,
            'difference_pp':delta,'rows':sorted(new,key=key,reverse=True),
            'older_rows':sorted(old,key=key,reverse=True),
            'profit_loss_rows':new,'older_profit_loss_rows':old,'excluded_date_symbols':excluded,
            'sold_rows':sold_groups[0],'older_sold_rows':sold_groups[1],'excluded_sold_count':excluded_sold,
            'method':'LastMonth: από τη μεταγενέστερη ημερομηνία μεταξύ αγοράς και 30 ημερών πριν, έως την ημερομηνία αναφοράς. Το συνολικό % = άθροισμα κέρδους/ζημιάς ÷ άθροισμα αξίας έναρξης για τις ίδιες καλυπτόμενες θέσεις. Total return from PD: απόδοση από την απόκτηση. Η μέση μηνιαία άνοδος είναι απλός μέσος από την απόκτηση, όχι LastMonth. Τα ποσά είναι εκτιμήσεις ανοικτών θέσεων με σταθερή ποσότητα, χωρίς μερικές συναλλαγές, μερίσματα, προμήθειες και ανασύνθεση ιστορικών ισοτιμιών.'}

    result['audit']=audit_review(result)
    if _platform_views:
        platform=lambda r:str(r.get('platform') or '').strip() or 'Χωρίς πλατφόρμα'
        names=sorted({platform(r) for r in list(stocks)+list(sold_stocks or [])})
        result['by_platform']={name:build_review([r for r in stocks if platform(r)==name],asof,news,histories,
            [r for r in sold_stocks or [] if platform(r)==name],_platform_views=False) for name in names}
    return result


def enrich_payload(payload, root=ROOT, network=True, budget_seconds=170):
    start=time.monotonic();root=Path(root)
    cache=load(root/'v21_research_cache.json')
    if network and os.getenv('V21_RESEARCH_ENABLED','1')=='1':
        with tempfile.TemporaryDirectory(prefix='metoxes_v21_') as tmp:
            inp=Path(tmp)/'input.json';out=Path(tmp)/'output.json'
            inp.write_text(json.dumps({'stocks':payload['stocks'],'candidates':payload['candidates'],'as_of':payload['generated_at'],'cache':cache},ensure_ascii=False),encoding='utf-8')
            # A separate process gives a hard wall-clock bound even if a vendor hangs.
            proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('portfolio_review_worker.py')),str(inp),str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL, start_new_session=(os.name != "nt"))
            try: proc.wait(timeout=max(0.1,min(float(budget_seconds),170)))
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
            updated=load(out)
            if updated:
                cache=updated
                dest=root/'v21_research_cache.json';temp=dest.with_suffix('.tmp')
                temp.write_text(json.dumps(clean(cache),ensure_ascii=False),encoding='utf-8');temp.replace(dest)
    snapshot=load(root/'investing_membership.json')
    asof=parse_date(payload['generated_at']) or date.today()
    for row in payload['candidates']:
        symbol=row.get('symbol'); b=(cache.get('betas') or {}).get(symbol,{})
        if number(b.get('beta')) is not None and (number(row.get('beta')) is None or str(b.get('beta_checked_at',''))>str(row.get('beta_checked_at',''))):
            row.update({k:b.get(k) for k in ('beta','beta_source','beta_source_url','beta_checked_at','low_52w')})
        row['beta']=number(row.get('beta'))
        row['beta_assessment']=beta_assessment(row['beta'])
        bd=parse_date(row.get('beta_checked_at'))
        row['beta_status']='missing' if row['beta'] is None else 'stale' if not bd or (asof-bd).days>7 else 'available'
        current,low=number(row.get('current_price')),number(row.get('low_52w'))
        row['distance_from_52w_low_pct']=round((current/low-1)*100,2) if current is not None and low and low>0 else None
        entry=(snapshot.get('candidates') or {}).get(symbol,{})
        checked=parse_date(entry.get('checked_at')); fresh=bool(checked and 0<=(asof-checked).days<=7)
        row['investing_undervalued']=entry.get('matched') if fresh else None
        row['investing_checked_at']=entry.get('checked_at')
        row['investing_source_url']=entry.get('source_url')
        row['investing_status']=('matched' if entry.get('matched') else 'not_in_list') if fresh and entry.get('matched') is not None else ('stale' if entry else 'not_checked')
        row['investing_scope']=entry.get('scope','Η εμφανιζόμενη λίστα Most Undervalued της αγοράς διαπραγμάτευσης, όχι το σύνολο υποτιμημένων μετοχών.')
    payload['quarter_review']=build_review(payload['stocks'],payload['generated_at'],cache.get('news'),cache.get('history_3m'),payload.get('sold_stocks',[]))
    payload['quarter_review']['research']={'elapsed_seconds':round(time.monotonic()-start,2),'hard_limit_seconds':min(budget_seconds,170),'sources':['Bloomberg','Reuters','Capital.gr','Ναυτεμπορική','Investing.com','Yahoo Finance','CNBC','MarketWatch'],'checked_at':cache.get('checked_at'),'status':cache.get('status','not_run')}
    payload['candidate_columns']=['final_score','beta','investing_undervalued','low_52w','discount_from_52w_high_pct','expand']
    try:
        from .extended_review_service import attach_extended
    except ImportError:
        from extended_review_service import attach_extended
    payload = attach_extended(payload, cache, snapshot)
    # V26: the standalone undervalued-stock screens were removed from the
    # dashboard. Drop old snapshot fields too, so they are not embedded again
    # when an existing portfolio_dashboard_data.json is refreshed.
    payload.pop('us_value_screen', None)
    payload.pop('investing_saved_lists', None)
    return clean(payload)
