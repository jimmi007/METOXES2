"""Import only visible saved Investing tables; never execute uploaded HTML."""
import json,re,unicodedata,hashlib
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime,timezone
from urllib.parse import urljoin,urlparse

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables=[];self.depth=0;self.table=None;self.row=None;self.cell=None;self.hidden=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table':
            self.depth+=1
            if self.depth==1:self.table=[]
        if self.depth!=1:return
        if tag=='tr':self.row=[]
        if tag in ('td','th'):self.cell={'text':'','links':[]}
        if tag=='a' and self.cell is not None:self.cell['links'].append(attrs.get('href',''))
        if tag in ('script','style'):self.hidden+=1
    def handle_data(self,text):
        if self.depth==1 and self.cell is not None and not self.hidden:self.cell['text']+=text+' '
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.hidden:self.hidden-=1
        if self.depth==1 and tag in ('td','th') and self.cell is not None:
            self.cell['text']=' '.join(self.cell['text'].split())
            if self.row is not None:self.row.append(self.cell)
            self.cell=None
        if self.depth==1 and tag=='tr' and self.row is not None:
            self.table.append(self.row);self.row=None
        if tag=='table':
            if self.depth==1:self.tables.append(self.table)
            self.depth=max(0,self.depth-1)

def normalized(name):
    text=''.join(c for c in unicodedata.normalize('NFKD',str(name)).casefold() if not unicodedata.combining(c))
    tokens=re.findall(r'[^\W_]+',text)
    return ' '.join(t for t in tokens if t not in {'inc','incorporated','corp','corporation','plc','ltd','limited'})

def parse_saved(path,country,snapshot_date):
    raw=Path(path).read_bytes();parser=TableParser();parser.feed(raw.decode('utf-8-sig',errors='replace'))
    slug='united-states' if country=='United States' else 'greece'
    source='https://gr.investing.com/equities/'+slug+'/most-undervalued'
    for table in parser.tables:
        for n,header in enumerate(table):
            names=[c['text'] for c in header]
            if not {'Όνομα','Upside','Εύλογη αξία'}.issubset(names):continue
            name_index=names.index('Όνομα');rows=[];seen=set()
            for cells in table[n+1:]:
                if len(cells)!=len(names):continue
                name=cells[name_index]['text']
                if not name or re.fullmatch(r'[Aa\s]+',name):raise ValueError('Hidden Investing names; import rejected')
                links=[urljoin(source,u) for u in cells[name_index]['links'] if '/equities/' in u]
                links=[u for u in links if urlparse(u).hostname in {'gr.investing.com','www.investing.com','investing.com'}]
                if not links:continue
                if links[0] in seen:continue
                seen.add(links[0]);rows.append({'rank':len(rows)+1,'name':name,'country':country,'source_url':links[0],
                    'fields':{k:c['text'] for k,c in zip(names,cells) if k},'snapshot_date':snapshot_date})
            if rows:return {'country':country,'source_url':source,'snapshot_date':snapshot_date,
                            'imported_at':datetime.now(timezone.utc).isoformat(),'filename':Path(path).name,
                            'sha256':hashlib.sha256(raw).hexdigest(),'rows':rows}
    raise ValueError('No readable Most Undervalued table found')

def attach_saved_lists(payload,root,cache):
    path=Path(root)/'investing_saved_lists.json'
    try:stored=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):stored={'lists':[]}
    lists=[]
    for saved in stored.get('lists',[]):
        result={k:v for k,v in saved.items() if k!='rows'};result['rows']=[]
        for item in saved.get('rows',[]):
            row=dict(item)
            quote=cache.get('saved_investing_quotes',{}).get(item['source_url'],{})
            row['quote']=quote
            try:
                from .imported_score_service import discount_from_high,number
            except ImportError:
                from imported_score_service import discount_from_high,number
            references=payload.get('candidates',[])+payload.get('stocks',[])
            matches=[x for x in references if (quote.get('symbol') and x.get('symbol')==quote['symbol']) or normalized(x.get('name',''))==normalized(item['name'])]
            unique={x.get('symbol') for x in matches if x.get('symbol')}
            reference=next((x for x in matches if number(x.get('final_score')) is not None),{}) if len(unique)==1 else {}
            score=quote.get('project_score') or {}
            if reference:
                score=dict(reference,checked_at=payload.get('generated_at'),scope='Ίδιο Final Score με την υπάρχουσα εγγραφή του dashboard.')
            row['final_score']=number(score.get('final_score'))
            row['score_details']={k:score.get(k) for k in ('fcf_yield','fcf_growth','roic','forward_revenue_growth','forward_eps_growth','score_rationale_text','score_model_label','scope','checked_at')}
            row['score_status']='available' if row['final_score'] is not None else 'pending'
            price,high=quote.get('current_price'),quote.get('high_52w')
            row['market_checked_at']=quote.get('checked_at')
            if discount_from_high(price,high) is None and reference:
                price,high=reference.get('current_price'),reference.get('high_52w')
                row['market_checked_at']=payload.get('generated_at')
            row['discount_from_52w_high_pct']=discount_from_high(price,high)
            row['current_price']=price;row['high_52w']=high
            result['rows'].append(row)
        lists.append(result)
    payload['investing_saved_lists']=lists
    return payload

def fetch_saved_quote(row):
    import yfinance as yf
    matches=[]
    for q in yf.Search(row['name'],max_results=8).quotes:
        allowed=q.get('exchange') in ({'ATH'} if row['country']=='Greece' else {'NMS','NGM','NCM','NYQ','ASE','PCX','BTS'})
        if allowed and normalized(row['name']) in {normalized(q.get('shortname','')),normalized(q.get('longname',''))}:
            if q.get('symbol'):matches.append(q['symbol'])
    symbols=set(matches)
    if len(symbols)!=1:return {'status':'unresolved','attempted_at':datetime.now(timezone.utc).isoformat()}
    symbol=symbols.pop();info=yf.Ticker(symbol).get_info()
    currency='EUR' if row['country']=='Greece' else 'USD'
    if info.get('symbol')!=symbol or info.get('currency')!=currency:raise ValueError('Quote identity mismatch')
    def num(v):
        import math
        try:return float(v) if math.isfinite(float(v)) else None
        except (ValueError,TypeError):return None
    result={'quote_version':25,'symbol':symbol,'beta':num(info.get('beta')),'low_52w':num(info.get('fiftyTwoWeekLow')),
            'current_price':num(info.get('currentPrice',info.get('regularMarketPrice'))),'high_52w':num(info.get('fiftyTwoWeekHigh')),
            'currency':currency,'checked_at':datetime.now(timezone.utc).isoformat(),'status':'matched',
            'source_url':'https://finance.yahoo.com/quote/'+symbol+'/key-statistics/'}

    try:
        from metoxes.services.candidate_research_service import _build_detailed_candidate
        result['fundamentals']=_build_detailed_candidate({'symbol':symbol,'name':row['name'],'exchange':info.get('exchange'),
            'country':info.get('country'),'sector':info.get('sector'),'current_price':result['current_price'],
            'high_52w':result['high_52w'],'currency':currency},set())
    except Exception:
        result['fundamentals_status']='unavailable'
    return result
