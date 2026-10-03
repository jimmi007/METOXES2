from pathlib import Path


def test_existing_holdings_are_wrapped_in_closed_master_details():
    text = Path("metoxes/services/dashboard_service.py").read_text(encoding="utf-8")
    assert '<details class="master-details" id="portfolioMaster">' in text
    assert '<summary class="master-summary">Υφιστάμενες Μετοχές' in text
    assert '<div id="portfolioAccordion" class="accordion-list"></div>' in text
    assert '<details class="master-details" id="portfolioMaster" open>' not in text


def test_master_arrow_css_is_present():
    text = Path("metoxes/services/dashboard_service.py").read_text(encoding="utf-8")
    assert '.master-summary::after{content:"▼"' in text
    assert '.master-details[open]>.master-summary::after{transform:rotate(180deg)}' in text
