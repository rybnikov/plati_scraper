import unittest

import plati_scrape


class ParsingTests(unittest.TestCase):
    def test_extract_duration_month_hyphen(self):
        self.assertEqual(
            plati_scrape.extract_duration("ChatGPT Pro 1-Month Activation"),
            "1 months",
        )

    def test_extract_duration_year_ru(self):
        self.assertEqual(
            plati_scrape.extract_duration("1 год подписка"),
            "1 years",
        )

    def test_parse_search_query_decodes(self):
        self.assertEqual(
            plati_scrape.parse_search_query("https://plati.market/search/claude%20code"),
            "claude code",
        )


if __name__ == "__main__":
    unittest.main()
