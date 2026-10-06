"""Private worker; parent terminates at 170s. Saves partial successes after each task."""
import concurrent.futures as cf
import json, os, re, subprocess, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from portfolio_review_service import number, parse_date, months_before
from extended_review_service import history_metrics
from us_value_service import UNIVERSE, fetch_quote, age_hours
from itertools import zip_longest
from investing_import_service import fetch_saved_quote

FEEDS={
 'finance.yahoo.com':'https://finance.yahoo.com/news/rssindex',
 'marketwatch.com':'https://feeds.content.dowjones.io/public/rss/mw_topstories',
 'investing.com':'https://www.investing.com/rss/news_25.rss',
 'cnbc.com':'https://www.cnbc.com/id/100003114/device/rss/rss.html',
}
DOMAINS=tuple(FEEDS)

def fetch_feed(domain,asof):
    # Generic public feed: no holdings, quantities, or names sent to the source.
    with urllib.request.urlopen(urllib.request.Request(FEEDS[domain],headers={'User-Agent':'METOXES2 RSS Reader'}),timeout=8) as response:
        xml=response.read(2_000_000)
    articles=[]
    for item in ET.fromstring(xml).findall('./channel/item'):
        try: published=parsedate_to_datetime(item.findtext('pubDate')).date()
        except Exception:continue
        if not asof-timedelta(days=31)<=published<=asof:continue
        articles.append({'title':item.findtext('title'),'url':item.findtext('link'),'source':domain,'published_at':published.isoformat(),'evidence':'headline_only'})
    return articles

def matches(row,article):
    title=(article.get('title') or '').lower()
    name=str(row.get('name') or '').lower()
    # Only specific company words; avoid symbols like ALB/ROP matching prose.
    terms=[t for t in re.findall(r'[a-zA-ZΑ-Ωα-ω]{4,}',name) if t not in {'incorporated','corporation','holdings','group','limited','international','technologies','technology','scientific','outdoor','pharmaceuticals'}]
    symbol=str(row.get('symbol','')).split('.')[0]
    return any(re.search(r'\b'+re.escape(t)+r'\b',title) for t in terms) or bool(re.search(r'\('+re.escape(symbol)+r'\)',article.get('title') or ''))

def fetch_beta(row):
    import yfinance as yf
    info=yf.Ticker(row['symbol']).get_info()
    return {'beta':number(info.get('beta')),'beta_source':'Yahoo Finance — Beta (5Y Monthly)','beta_checked_at':datetime.now(timezone.utc).isoformat(),'low_52w':number(info.get('fiftyTwoWeekLow'))}

def fetch_history(symbol, asof):
    import yfinance as yf
    ticker=yf.Ticker(symbol)
    frame=ticker.history(start=str(months_before(asof,3)-timedelta(days=8)), end=str(asof+timedelta(days=1)), auto_adjust=False, timeout=10)
    points=[{'date':str(index.date()),'close':number(row.get('Close')),'adjusted_close':number(row.get('Adj Close'))} for index,row in frame.iterrows()]
    result=history_metrics(points,asof)
    result['currency']=ticker.get_history_metadata().get('currency')
    return result


def fetch_investing_quote(row):
    import yfinance as yf
    # Only unambiguous exact normalized company-name matches on US exchanges.
    root=Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    from sync_investing import normalize
    quotes=yf.Search(row['name'],max_results=8).quotes
    matches=[q for q in quotes if q.get('exchange') in {'NMS','NGM','NCM','NYQ','ASE','PCX','BTS'}
             and normalize(row['name']) in {normalize(q.get('shortname','')),normalize(q.get('longname',''))}]
    symbols={q.get('symbol') for q in matches if q.get('symbol')}
    if len(symbols)!=1:return {'symbol':None,'match_status':'unresolved','beta':None,'low_52w':None}
    symbol=symbols.pop()
    info=yf.Ticker(symbol).get_info()
    return {'symbol':symbol,'match_status':'exact_name_us_exchange','beta':number(info.get('beta')),
            'low_52w':number(info.get('fiftyTwoWeekLow')),'high_52w':number(info.get('fiftyTwoWeekHigh')),
            'current_price':number(info.get('currentPrice',info.get('regularMarketPrice'))),
            'currency':info.get('currency'),'beta_checked_at':datetime.now(timezone.utc).isoformat(),
            'beta_source':'Yahoo Finance — Beta (5Y Monthly)','beta_source_url':'https://finance.yahoo.com/quote/'+urllib.parse.quote(symbol,safe='')+'/'}


def explain(articles):
    text=' '.join(a['title'] or '' for a in articles).lower()
    topics=[]
    for words,label in [(['earnings','guidance','profit','revenue'],'αποτελέσματα και προβλέψεις'),(['upgrade','downgrade','price target','analyst'],'αλλαγές εκτιμήσεων αναλυτών'),(['tariff','trade war'],'δασμούς και εμπορική πολιτική'),(['contract','launch','satellite'],'συμβάσεις ή νέες εκτοξεύσεις/προϊόντα'),(['ai ','data center','datacenter'],'ζήτηση υποδομών AI'),(['approval','trial','fda'],'κλινικά ή ρυθμιστικά νέα'),(['lithium','commodity','gold'],'τιμές πρώτων υλών')]:
        if any(w in text for w in words): topics.append(label)
    if not articles:return 'Δεν βρέθηκε επαρκής τεκμηρίωση στο συγκεκριμένο χρονικό διάστημα. Δεν αποδίδεται αιτία στη μεταβολή.'
    if topics:return 'Οι πρόσφατοι τίτλοι αναφέρονται σε '+', '.join(topics)+'. Πρόκειται για πιθανό πλαίσιο της μεταβολής, όχι επιβεβαιωμένη αιτία· η εκτίμηση βασίζεται σε τίτλους. Δείτε τις ημερομηνίες και τις πηγές παρακάτω.'
    return 'Βρέθηκαν πρόσφατοι σχετικοί τίτλοι, αλλά δεν προκύπτει ασφαλής εξήγηση της μεταβολής μόνο από αυτούς. Παρατίθενται για έλεγχο.'

def main():
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));out=Path(sys.argv[2])
    cache=request.get('cache') or {};cache.setdefault('news',{});cache.setdefault('betas',{});cache.setdefault('history_3m',{});cache.setdefault('investing_quotes',{});cache.setdefault('us_value_quotes',{});cache.setdefault('us_value_errors',{});cache.setdefault('saved_investing_quotes',{})
    asof=parse_date(request['as_of']);cutoff=months_before(asof,3);now=datetime.now(timezone.utc)
    def fresh(v,hours):
        try:return 0<=(now-datetime.fromisoformat(v).astimezone(timezone.utc)).total_seconds()<hours*3600
        except Exception:return False
    def save():
        temp=out.with_suffix('.tmp');temp.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8');temp.replace(out)
    recent={r['symbol']:r for r in request['stocks'] if parse_date(r.get('purchase_date')) and cutoff<=parse_date(r['purchase_date'])<=asof}
    pool=cf.ThreadPoolExecutor(max_workers=6);jobs={}
    root=Path(__file__).resolve().parents[2]
    pending={}
    for symbol,row in recent.items():
        existing=cache['news'].get(symbol,{})
        if fresh(existing.get('checked_at'),6) and existing.get('as_of')==str(asof):continue
        pending[symbol]=row
        retained=[a for a in existing.get('articles',[]) if parse_date(a.get('published_at')) and asof-timedelta(days=31)<=parse_date(a['published_at'])<=asof]
        cache['news'][symbol]={'articles':retained,'source_status':{},'as_of':str(asof),'checked_at':now.isoformat(),'summary':explain(retained)}
    if pending:
        for domain in DOMAINS:jobs[pool.submit(fetch_feed,domain,asof)]=('feed','',domain)
    history_symbols=[symbol for symbol in dict.fromkeys(r.get('symbol') for r in request['stocks'] if r.get('symbol'))
        if not(cache['history_3m'].get(symbol,{}).get('as_of')==str(asof) and cache['history_3m'][symbol].get('status')=='available')]
    value_symbols=[symbol for symbol in UNIVERSE
        if not fresh(cache['us_value_quotes'].get(symbol,{}).get('checked_at'),24)
        and not fresh(cache['us_value_errors'].get(symbol,{}).get('checked_at'),.25)]
    value_symbols.sort(key=lambda s:cache['us_value_errors'].get(s,{}).get('checked_at',''))
    for value_symbol,history_symbol in zip_longest(value_symbols,history_symbols):
        if value_symbol:jobs[pool.submit(fetch_quote,value_symbol)]=('us_value',value_symbol,None)
        if history_symbol:jobs[pool.submit(fetch_history,history_symbol,asof)]=('history',history_symbol,None)
    for row in request['candidates']:
        if number(row.get('beta')) is not None and fresh(row.get('beta_checked_at'),168):continue
        if fresh(cache['betas'].get(row['symbol'],{}).get('beta_checked_at'),168):continue
        jobs[pool.submit(fetch_beta,row)]=('beta',row['symbol'],None)
    try: saved=json.loads((root/'investing_saved_lists.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):saved={}
    for group in saved.get('lists',[]):
        for row in group.get('rows',[]):
            key=row['source_url'];previous=cache['saved_investing_quotes'].get(key,{})
            if fresh(previous.get('checked_at') or previous.get('attempted_at'),24):continue
            jobs[pool.submit(fetch_saved_quote,row)]=('saved_quote',key,None)
    cache['checked_at']=now.isoformat();cache['status']='partial';save()
    for future in cf.as_completed(jobs):
        kind,symbol,domain=jobs[future]
        try:
            result=future.result()
            if kind=='saved_quote':cache['saved_investing_quotes'][symbol]=result
            elif kind=='us_value':
                cache['us_value_quotes'][symbol]=result
                cache['us_value_errors'].pop(symbol,None)
            elif kind=='history':cache['history_3m'][symbol]=result
            elif kind=='beta' and number(result.get('beta')) is not None:cache['betas'][symbol]=result
            elif kind=='investing': cache['investing_sync_status']='complete' if result.returncode==0 else 'unavailable'
            elif kind=='feed':
                for symbol,row in pending.items():
                    selected=[a for a in result if matches(row,a)][:3]
                    r=cache['news'][symbol];r['articles']=list({a['url']:a for a in r['articles']+selected}.values());r['source_status'][domain]='ok' if selected else 'no_matching_headlines';r['summary']=explain(r['articles'])
        except Exception as error:
            if kind=='saved_quote':cache['saved_investing_quotes'][symbol]={'status':'unavailable','attempted_at':datetime.now(timezone.utc).isoformat()}
            if kind=='saved_quote':cache['saved_investing_quotes'][symbol]=result
            elif kind=='us_value':cache['us_value_errors'][symbol]={'checked_at':datetime.now(timezone.utc).isoformat(),'reason':type(error).__name__}
            if kind=='feed':
                for symbol in pending:cache['news'][symbol]['source_status'][domain]='unavailable'

        save()
    pool.shutdown(wait=False);cache['status']='completed_with_results' if any(r.get('articles') for r in cache['news'].values()) else 'no_news_evidence';save()
if __name__=='__main__':main()
