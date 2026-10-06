"""Transparent US value screen; sector comparison, not a fair-value forecast."""
import math
from datetime import datetime, timezone
from statistics import median

# Fixed, inspectable universe. Financials/REITs excluded: FCF is not comparable.
UNIVERSE = '''AAPL MSFT ORCL CSCO IBM QCOM TXN AMAT
GOOGL META NFLX DIS CMCSA VZ T CHTR
AMZN HD LOW TGT NKE SBUX GM F
PG KO PEP WMT COST KR KMB CL
JNJ MRK PFE ABBV AMGN GILD BMY CVS
CAT DE HON GE UPS FDX LMT RTX
XOM CVX COP EOG OXY DVN HAL SLB
LIN APD SHW DOW DD NUE STLD FCX'''.split()

def numeric(x):
    try:
        value=float(x)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):return None

def age_hours(timestamp, now=None):
    try:
        dt=datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return ((now or datetime.now(timezone.utc))-dt).total_seconds()/3600
    except (TypeError,ValueError):return math.inf

def fetch_quote(symbol):
    import yfinance as yf
    info=yf.Ticker(symbol).get_info()
    if not info or info.get('symbol') != symbol:raise ValueError('Missing/mismatched quote')
    fields={'name':'longName','sector':'sector','country':'country','currency':'currency','quote_type':'quoteType',
            'market_cap':'marketCap','current_price':'currentPrice','forward_pe':'forwardPE',
            'free_cash_flow':'freeCashflow','profit_margin':'profitMargins','roe':'returnOnEquity',
            'revenue_growth':'revenueGrowth','beta':'beta','low_52w':'fiftyTwoWeekLow','high_52w':'fiftyTwoWeekHigh'}
    row={k:info.get(v) for k,v in fields.items()}
    for k in fields:
        if k not in {'name','sector','country','currency','quote_type'}:row[k]=numeric(row[k])
    row['current_price']=row['current_price'] or numeric(info.get('regularMarketPrice'))
    row.update(symbol=symbol,checked_at=datetime.now(timezone.utc).isoformat(),source_url='https://finance.yahoo.com/quote/'+symbol+'/key-statistics/')
    if not row['current_price'] or not row['market_cap']:raise ValueError('Incomplete quote')
    return row

def build_screen(cache, holdings=(), now=None):
    now=now or datetime.now(timezone.utc)
    stored=cache.get('us_value_quotes',{})
    fresh=[dict(stored[s]) for s in UNIVERSE if s in stored and 0<=age_hours(stored[s].get('checked_at'),now)<=24]
    eligible_base=[r for r in fresh if r.get('country')=='United States' and r.get('currency')=='USD'
                   and r.get('quote_type')=='EQUITY' and (numeric(r.get('market_cap')) or 0)>=2e9
                   and r.get('sector') and r['sector'] not in {'Financial Services','Real Estate'}]
    results=[];excluded={};holdings=set(holdings)
    def exclude(reason):excluded[reason]=excluded.get(reason,0)+1
    for row in eligible_base:
        pe=numeric(row.get('forward_pe'));fcf=numeric(row.get('free_cash_flow'))
        margin=numeric(row.get('profit_margin'));roe=numeric(row.get('roe'));growth=numeric(row.get('revenue_growth'))
        if any(v is None for v in (pe,fcf,margin,roe,growth)):
            exclude('missing_metrics');continue
        if not (0<pe<=150 and fcf>0 and margin>0 and roe>0 and growth>=-.10):
            exclude('profitability_or_growth_filter');continue
        peers=[p for p in eligible_base if p.get('sector')==row['sector'] and p['symbol']!=row['symbol']
               and numeric(p.get('forward_pe')) is not None and 0<float(p['forward_pe'])<=150]
        if len(peers)<4:
            exclude('insufficient_sector_peers');continue
        pe_median=median(float(p['forward_pe']) for p in peers)
        ratio=pe/pe_median;fcf_yield=100*fcf/row['market_cap']
        if ratio>.85 and fcf_yield<5:
            exclude('no_value_signal');continue
        clip=lambda x,maximum:max(0,min(maximum,x))
        components={'relative_pe':round(clip((1.5-ratio)*30,30),2),'fcf_yield':round(clip(fcf_yield/8*30,30),2),
                    'roe':round(clip(roe/.20*20,20),2),'profit_margin':round(clip(margin/.20*10,10),2),
                    'revenue_growth':round(clip(growth/.15*10,10),2)}
        score=round(sum(components.values()),2)
        if score<60:exclude('score_below_60');continue
        price,low=numeric(row.get('current_price')),numeric(row.get('low_52w'))
        row.update(value_score=score,components=components,fcf_yield_pct=round(fcf_yield,2),
                   peer_forward_pe=round(pe_median,2),peer_count=len(peers),peer_symbols=[p['symbol'] for p in peers],
                   pe_discount_pct=round((1-ratio)*100,2),already_in_portfolio=row['symbol'] in holdings,
                   distance_from_52w_low_pct=round((price/low-1)*100,2) if price and low and low>0 else None)
        row['rationale']=f"Forward P/E {pe:.2f} έναντι διαμέσου κλάδου {pe_median:.2f} ({len(peers)} εταιρείες). FCF yield {fcf_yield:.2f}%, ROE {roe*100:.2f}%, καθαρό περιθώριο {margin*100:.2f}%, αύξηση εσόδων {growth*100:.2f}%."
        row['risks']=['Η σύγκριση είναι με εταιρείες του ίδιου ευρύτερου κλάδου· δεν εξισώνει επιχειρηματικά μοντέλα.',
                      'Χαμηλό P/E ή υψηλό FCF yield μπορεί να αντανακλά πτώση κερδών ή έκτακτες ταμειακές ροές.',
                      'Το ROE επηρεάζεται από μόχλευση και επαναγορές. Το score δεν έχει ακόμη επαληθευτεί με backtesting.']
        results.append(row)
    results.sort(key=lambda r:(-r['value_score'],r['symbol']))
    for i,row in enumerate(results,1):row['rank']=i
    stale=sum(1 for s in UNIVERSE if s in stored and age_hours(stored[s].get('checked_at'),now)>24)
    return {'rows':results,'universe_size':len(UNIVERSE),'universe':UNIVERSE,'fresh_count':len(fresh),
            'eligible_base_count':len(eligible_base),'stale_count':stale,'excluded':excluded,
            'status':'complete' if len(fresh)==len(UNIVERSE) else 'partial' if fresh else 'unavailable',
            'checked_at':max((r['checked_at'] for r in fresh),default=None),'evaluated_at':now.isoformat(),
            'last_errors':cache.get('us_value_errors',{}),
            'method':'Σταθερό δείγμα 64 συμβόλων, όχι όλη η αγορά ΗΠΑ. Ελέγχονται εταιρείες ΗΠΑ, USD, κεφαλαιοποίηση ≥ $2 δισ. Εξαιρούνται χρηματοοικονομικά/REITs. Τουλάχιστον 4 άλλες εταιρείες ανά κλάδο. Θετικά κέρδη, FCF και ROE, μεταβολή εσόδων ≥ −10%. Ένδειξη αξίας: forward P/E τουλάχιστον 15% κάτω από τη διάμεσο κλάδου ή FCF yield ≥ 5%. Score ≥ 60/100: σχετικό P/E 30, FCF yield 30, ROE 20, περιθώριο 10, ανάπτυξη εσόδων 10. Beta/52W εμφανίζονται χωρίς να επηρεάζουν το score. Δεδομένα παλαιότερα των 24 ωρών εξαιρούνται. Ένδειξη υποτίμησης, όχι υπολογισμός εύλογης αξίας ή πιθανότητα κέρδους.'}
