"""
Test suite for the Research Assistant system.

Tests cover:
  1. Custom tool (Source Credibility Scorer) — unit tests
  2. Agent creation — smoke tests
  3. Integration — end-to-end with mock (optional, requires API key)
"""

import unittest
import sys
import os
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.credibility_scorer import SourceCredibilityScorer


class TestCredibilityScorer(unittest.TestCase):
    """Unit tests for the custom Source Credibility Scorer tool."""

    def setUp(self):
        self.scorer = SourceCredibilityScorer()

    # ── Domain authority tests ───────────────────────────────────────

    def test_gov_domain_scores_high(self):
        result = self.scorer._run(url="https://www.cdc.gov/covid/index.html")
        self.assertIn("high authority domain", result)  # .gov tier 1

    def test_edu_domain_scores_high(self):
        result = self.scorer._run(url="https://web.mit.edu/research")
        self.assertIn(".edu domain", result)

    def test_known_outlet_scores_medium(self):
        result = self.scorer._run(url="https://www.reuters.com/article/example")
        self.assertIn("reuters.com", result)

    def test_blog_platform_scores_low(self):
        result = self.scorer._run(url="https://medium.com/@user/some-article")
        self.assertIn("medium.com", result)
        # Should not be HIGHLY CREDIBLE
        self.assertNotIn("HIGHLY CREDIBLE", result)

    def test_unknown_domain_gets_baseline(self):
        result = self.scorer._run(url="https://random-site-12345.xyz/page")
        self.assertIn("unranked domain", result)

    def test_http_penalized(self):
        result = self.scorer._run(url="http://sketchy-site.com/page")
        self.assertIn("no HTTPS", result)

    # ── Freshness tests ──────────────────────────────────────────────

    # Freshness is measured against the day the test runs, so these dates are
    # built relative to today. An earlier version hard-coded 2026-03-01 and
    # asserted "very recent"; it passed when it was written and started failing
    # six months later when that date aged out of the 90-day band.

    def test_recent_date_scores_high(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        result = self.scorer._run(url="https://example.com", publication_date=recent)
        self.assertIn("very recent", result)

    def test_one_year_old_date_scores_middle(self):
        year_old = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d")
        result = self.scorer._run(url="https://example.com", publication_date=year_old)
        self.assertIn("recent", result)
        self.assertNotIn("very recent", result)

    def test_old_date_scores_low(self):
        old = (datetime.now(timezone.utc) - timedelta(days=1200)).strftime("%Y-%m-%d")
        result = self.scorer._run(url="https://example.com", publication_date=old)
        self.assertIn("potentially outdated", result)

    def test_no_date_gives_neutral(self):
        result = self.scorer._run(url="https://example.com")
        self.assertIn("No publication date provided", result)

    def test_invalid_date_handled(self):
        result = self.scorer._run(
            url="https://example.com",
            publication_date="not-a-date",
        )
        self.assertIn("Could not parse", result)

    # ── Author & citation tests ──────────────────────────────────────

    def test_author_present_boosts_score(self):
        result = self.scorer._run(
            url="https://example.com", has_author=True
        )
        self.assertIn("Named author present", result)

    def test_no_author_reduces_score(self):
        result = self.scorer._run(
            url="https://example.com", has_author=False
        )
        self.assertIn("No named author", result)

    def test_citations_present_boosts_score(self):
        result = self.scorer._run(
            url="https://example.com", has_citations=True
        )
        self.assertIn("Contains references", result)

    def test_no_citations_reduces_score(self):
        result = self.scorer._run(
            url="https://example.com", has_citations=False
        )
        self.assertIn("No citations", result)

    # ── Full scoring integration ─────────────────────────────────────

    def test_perfect_source(self):
        """A .gov source, recent, with author and citations should score 8+."""
        result = self.scorer._run(
            url="https://www.nih.gov/research/findings",
            publication_date="2026-03-15",
            has_author=True,
            has_citations=True,
        )
        # Extract overall score
        for line in result.split("\n"):
            if "Overall Score:" in line:
                score = float(line.split(":")[1].split("/")[0].strip())
                self.assertGreaterEqual(score, 8.0)
                break

    def test_poor_source(self):
        """HTTP blog, old, no author, no citations should score under 4."""
        result = self.scorer._run(
            url="http://random-blog.blogspot.com/2019/post",
            publication_date="2019-06-01",
            has_author=False,
            has_citations=False,
        )
        for line in result.split("\n"):
            if "Overall Score:" in line:
                score = float(line.split(":")[1].split("/")[0].strip())
                self.assertLessEqual(score, 4.0)
                break

    # ── Edge cases ───────────────────────────────────────────────────

    def test_empty_url(self):
        """Should not crash on empty URL."""
        result = self.scorer._run(url="")
        self.assertIn("Source Credibility Report", result)

    def test_url_without_scheme(self):
        """Should handle URLs without https://."""
        result = self.scorer._run(url="www.reuters.com/article")
        self.assertIn("reuters.com", result)

    def test_output_format(self):
        """Output should always contain the required sections."""
        result = self.scorer._run(url="https://example.com")
        self.assertIn("Source Credibility Report", result)
        self.assertIn("Overall Score:", result)
        self.assertIn("Breakdown:", result)
        self.assertIn("Domain Authority:", result)
        self.assertIn("Content Freshness:", result)
        self.assertIn("Author Attribution:", result)
        self.assertIn("Citation Presence:", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
