"""Read visible Investing tables with your own Chrome session. No passwords in code."""
import argparse,json,re,time,unicodedata
from datetime import datetime,timezone
from pathlib import Path

COUNTRIES={'United States':'united-states','United Kingdom':'united-kingdom','Sweden':'sweden','Portugal':'portugal','Spain':'spain','Germany':'germany','France':'france'}
def normalize(name):
    name=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()
    tokens=re.findall(r'[a-z0-9]+',name)
    return ' '.join(t for t in tokens if t not in {'plc','inc','incorporated','corp','corporation','sa','s','a','ab','publ','ag','sgps','ltd','limited'})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--login',action='store_true');args=ap.parse_args()
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    root=Path(__file__).resolve().parent
    options=webdriver.ChromeOptions()
    if not args.login:options.add_argument('--headless=new')
    options.add_argument('--user-data-dir='+str(root/'investing_chrome_profile'))
    driver=webdriver.Chrome(options=options);driver.set_page_load_timeout(15)
    try:
        if args.login:
            driver.get('https://gr.investing.com/equities/united-states/most-undervalued')
            input('Sign in directly in Chrome, then press Enter here. No password is read by this script. ')
        payload=json.loads((root/'portfolio_dashboard_data.json').read_text(encoding='utf-8'))
        oldpath=root/'investing_membership.json'
        result=json.loads(oldpath.read_text(encoding='utf-8')) if oldpath.exists() else {'candidates':{}}
        started=time.monotonic()
        for country,slug in COUNTRIES.items():
            rows=[r for r in payload['candidates'] if r.get('exchange_country',r.get('country'))==country or (not r.get('exchange_country') and r.get('country')==country)]
            if not rows:continue
            if time.monotonic()-started>150:break
            url='https://gr.investing.com/equities/'+slug+'/most-undervalued'
            try:
                driver.get(url)
                # Visible page only; stop at access/auth challenges, never bypass them.
                text=driver.find_element(By.TAG_NAME,'body').text.lower()
                if any(t in text for t in ('verify you are human','checking your browser','access denied','just a moment')):
                    print('Verification required; stopping Investing.');break
                tables=driver.find_elements(By.TAG_NAME,'table')
                if not tables:continue
                names=[a.text.strip() for a in tables[0].find_elements(By.CSS_SELECTOR,'tbody tr td:first-child a') if a.text.strip()]
                if not names or any(re.fullmatch(r'[Aa\s]+',n) for n in names):
                    print(country+': list unavailable or names hidden; previous results retained.');continue
                nameset={normalize(n) for n in names}
                for row in rows:
                    result['candidates'][row['symbol']]={'matched':normalize(row.get('name','')) in nameset,'checked_at':datetime.now(timezone.utc).isoformat(),'source_url':url,'scope':f'Visible Most Undervalued table, {len(names)} companies; normalized exact company-name match.','country':country}
                temp=oldpath.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(oldpath)
                print(country+': checked '+str(len(rows))+' candidates.')
            except Exception as error: print(country+': unavailable ('+type(error).__name__+').')
        print('Run POST /stocks/update-excel to show the updated checks.')
    finally:driver.quit()
if __name__=='__main__':main()
