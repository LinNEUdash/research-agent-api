"""Tests for the scrape ceiling.

The upstream tool is not called here. What matters is the ceiling applied to
whatever it returns, so the parent's _run is patched and the subclass is
exercised on its own.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import MAX_SCRAPE_CHARS
from tools.bounded_scraper import BoundedScrapeWebsiteTool

PARENT_RUN = "crewai_tools.ScrapeWebsiteTool._run"


class TestBoundedScraper(unittest.TestCase):

    def setUp(self):
        self.tool = BoundedScrapeWebsiteTool()

    def test_short_page_passes_through_unchanged(self):
        page = "a short article"
        with patch(PARENT_RUN, return_value=page):
            self.assertEqual(self.tool._run(website_url="https://example.com"), page)

    def test_page_at_the_limit_is_not_truncated(self):
        page = "x" * MAX_SCRAPE_CHARS
        with patch(PARENT_RUN, return_value=page):
            result = self.tool._run(website_url="https://example.com")
        self.assertEqual(result, page)
        self.assertNotIn("Truncated", result)

    def test_long_page_is_cut_to_the_limit(self):
        page = "x" * (MAX_SCRAPE_CHARS + 50_000)
        with patch(PARENT_RUN, return_value=page):
            result = self.tool._run(website_url="https://example.com")
        self.assertEqual(result.count("x"), MAX_SCRAPE_CHARS)

    def test_truncation_is_announced_to_the_model(self):
        """A silent cut would let the model treat a fragment as the whole page."""
        page = "x" * (MAX_SCRAPE_CHARS + 1)
        with patch(PARENT_RUN, return_value=page):
            result = self.tool._run(website_url="https://example.com")
        self.assertIn("Truncated", result)
        self.assertIn("partial read", result)

    def test_leading_content_is_the_part_kept(self):
        page = "HEADLINE AND OPENING. " + ("filler " * 50_000)
        with patch(PARENT_RUN, return_value=page):
            result = self.tool._run(website_url="https://example.com")
        self.assertTrue(result.startswith("HEADLINE AND OPENING."))

    def test_non_string_result_is_left_alone(self):
        """The upstream tool is typed as returning Any; do not assume str."""
        with patch(PARENT_RUN, return_value=None):
            self.assertIsNone(self.tool._run(website_url="https://example.com"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
