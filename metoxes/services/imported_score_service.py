"""Score imported companies through the existing candidate scoring pipeline."""
from datetime import datetime,timezone
from copy import deepcopy
import math

def number(v):
    try:return float(v) if math.isfinite(float(v)) else None
    except (ValueError,TypeError):return None

def discount_from_high(price,high):
    price,high=number(price),number(high)
    return round((1-price/high)*100,2) if price is not None and price>0 and high is not None and high>0 else None

def score_imported(cache,references):
    from metoxes.services.scoring_services import score_stocks_by_sector
    from metoxes.services.candidate_research_service import _apply_forward_scores
    from metoxes.services.absolute_quality_service import add_absolute_quality_scores
    from metoxes.services.financial_sector_scoring_service import apply_financial_sector_model
    quotes=cache.get('saved_investing_quotes',{})
    base={r['symbol']:deepcopy(r) for r in references if r.get('symbol')}
    targets={}
    for key,q in quotes.items():
        row=q.get('fundamentals')
        if not row or not row.get('symbol'):continue
        if row.get('sector')!='Financial Services' and sum(number(row.get(k)) is not None for k in ('fcf_yield','fcf_growth','roic','forward_revenue_growth','forward_eps_growth'))<3:continue
        base[row['symbol']]=deepcopy(row);targets[key]=row['symbol']
    if not targets:return
    scored=score_stocks_by_sector(list(base.values()))
    scored=_apply_forward_scores(scored)
    scored=add_absolute_quality_scores(scored)
    scored=apply_financial_sector_model(scored,workers=2)
    by_symbol={r['symbol']:r for r in scored}
    fields=('final_score','fcf_yield','fcf_growth','roic','forward_revenue_growth','forward_eps_growth',
            'score_rationale_text','score_model_label','absolute_coverage','financial_model','sector','country')
    for key,symbol in targets.items():
        row=by_symbol.get(symbol,{})
        coverage=number(row.get('absolute_coverage'))
        if row.get('sector')!='Financial Services' and (coverage is None or coverage<60):continue
        if number(row.get('final_score')) is None:continue
        quotes[key]['project_score']={k:row.get(k) for k in fields}
        quotes[key]['project_score']['checked_at']=datetime.now(timezone.utc).isoformat()
        quotes[key]['project_score']['scope']='Ίδια ακολουθία βαθμολόγησης υποψήφιων του project. Δείγμα σύγκρισης: υφιστάμενες, υποψήφιες και εισαγμένες εταιρείες με διαθέσιμα δεδομένα. Το διαφορετικό δείγμα μπορεί να αλλάξει το σχετικό σκέλος.'
