"""V21: auditable cohorts and time-bounded enrichment. No credentials in output."""
from __future__ import annotations
import calendar, json, math, os, re, signal, subprocess, sys, tempfile, time
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]

def number(v):
    try:
        n=float(v)
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

def build_review(stocks, asof, news=None):
    asof=parse_date(asof) or date.today(); cutoff=months_before(asof,3)
    new=[];old=[];excluded=[]
    for r in stocks:
        d=parse_date(r.get('purchase_date'))
        if not d or d>asof: excluded.append(r.get('symbol'));continue
        (new if d>=cutoff else old).append(r)
    a,b=cohort_stats(new),cohort_stats(old)
    delta=a['mean_monthly_pct']-b['mean_monthly_pct'] if a['mean_monthly_pct'] is not None and b['mean_monthly_pct'] is not None else None
    rows=[]
    for r in sorted(new,key=lambda x:number(x.get('monthly_percent_change')) if number(x.get('monthly_percent_change')) is not None else -1e9,reverse=True):
        x={k:r.get(k) for k in ('symbol','name','platform','purchase_date','purchase_price','current_price','percent_change','monthly_percent_change')}
        x['monthly_includes_pre_purchase']=(asof-parse_date(r['purchase_date'])).days<30
        x['news']=(news or {}).get(r.get('symbol'),{})
        rows.append(x)
    return {'as_of':asof.isoformat(),'cutoff':cutoff.isoformat(),'recent':a,'older':b,'difference_pp':round(delta,4) if delta is not None else None,'rows':rows,'excluded_date_symbols':excluded,
      'method':'Κυλιόμενο τρίμηνο 3 ημερολογιακών μηνών, με συμπερίληψη της πρώτης ημέρας. Σύγκριση L = monthly_percent_change, σε ποσοστιαίες μονάδες. Απλός μέσος ανά ticker (ίδιο ticker σε brokers μετρά μία φορά ανά ομάδα). Οι διαφορετικές καταχωρίσεις ETF παραμένουν χωριστές. Η συνολική απόδοση από αγορά σταθμίζεται με το αρχικό κόστος στις τιμές του portfolio και αφορά διαφορετικές διάρκειες κατοχής. Δεν είναι τριμηνιαία απόδοση. Η L μπορεί να περιλαμβάνει ημέρες πριν από την αγορά. Οι ειδήσεις δίνουν πιθανό πλαίσιο, όχι απόδειξη αιτιότητας.'}

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
    payload['quarter_review']=build_review(payload['stocks'],payload['generated_at'],cache.get('news'))
    payload['quarter_review']['research']={'elapsed_seconds':round(time.monotonic()-start,2),'hard_limit_seconds':min(budget_seconds,170),'sources':['Yahoo Finance','CNBC','MarketWatch','Investing.com'],'checked_at':cache.get('checked_at'),'status':cache.get('status','not_run')}
    payload['candidate_columns']=['final_score','beta','investing_undervalued','low_52w','discount_from_52w_high_pct','expand']
    return clean(payload)
