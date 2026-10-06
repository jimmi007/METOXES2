import tempfile
import unittest
from pathlib import Path

from metoxes.services.dashboard_service import HTML_TEMPLATE
from metoxes.services.portfolio_review_service import enrich_payload


class DashboardV26Tests(unittest.TestCase):
    def test_removed_standalone_undervalued_sections(self):
        self.assertNotIn('id="savedInvestingLists"', HTML_TEMPLATE)
        self.assertNotIn('id="usValueScreen"', HTML_TEMPLATE)
        self.assertNotIn('renderUSValue();renderSavedInvesting();', HTML_TEMPLATE)

    def test_candidate_country_and_menu_colours_are_present(self):
        self.assertIn('className="country-badge"', HTML_TEMPLATE)
        self.assertIn('candidateMaster>.master-summary', HTML_TEMPLATE)
        self.assertIn('portfolioMaster>.master-summary', HTML_TEMPLATE)

    def test_old_list_payload_is_removed_on_refresh(self):
        payload = {
            'generated_at': '2026-10-05T12:00:00',
            'stocks': [],
            'candidates': [],
            'quality': {},
            'us_value_screen': {'rows': [1]},
            'investing_saved_lists': [{'country': 'Greece'}],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = enrich_payload(payload, root=Path(directory), network=False)
        self.assertNotIn('us_value_screen', result)
        self.assertNotIn('investing_saved_lists', result)


if __name__ == '__main__':
    unittest.main()
