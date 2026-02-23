import unittest

import mcp_server


class McpServerTests(unittest.TestCase):
    def test_parse_query_input_search_root_is_empty(self):
        parsed = mcp_server._parse_query_input("https://plati.market/search/")
        self.assertEqual(parsed["product_query"], "")
        self.assertEqual(parsed["category_id"], "")

    def test_parse_query_input_search_query_param(self):
        parsed = mcp_server._parse_query_input("https://plati.market/search/?q=claude%20code")
        self.assertEqual(parsed["product_query"], "claude code")
        self.assertEqual(parsed["category_id"], "")

    def test_parse_query_input_category_url(self):
        parsed = mcp_server._parse_query_input("https://plati.market/games/cyberpunk-2077/831/")
        self.assertEqual(parsed["product_query"], "cyberpunk 2077")
        self.assertEqual(parsed["category_id"], "831")

    def test_split_terms(self):
        terms = mcp_server._split_terms("pro, 12m | account;plus")
        self.assertEqual(terms, ["pro", "12m", "account", "plus"])

    def test_sort_lots_price_desc(self):
        rows = [
            {"title": "a", "min_option_price": 100.0, "seller_reviews": 10, "positive_ratio": 0.99},
            {"title": "b", "min_option_price": 300.0, "seller_reviews": 5, "positive_ratio": 0.95},
            {"title": "c", "min_option_price": 200.0, "seller_reviews": 99, "positive_ratio": 0.98},
        ]
        out = mcp_server._sort_lots(rows, "price_desc")
        self.assertEqual([x["title"] for x in out], ["b", "c", "a"])

    def test_empty_search_query_raises(self):
        with self.assertRaises(ValueError):
            mcp_server.find_cheapest_reliable_options("https://plati.market/search/", limit=1)


if __name__ == "__main__":
    unittest.main()
