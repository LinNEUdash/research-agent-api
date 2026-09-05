"""
Custom Tool: Source Credibility Scorer

Evaluates the credibility of a web source based on multiple factors:
- Domain authority (e.g., .edu, .gov, known outlets)
- Content freshness (publication date)
- Source transparency (author attribution, citations)

Inputs:  URL string (required), optional publication date
Outputs: Credibility score (1-10), breakdown by factor, recommendation

Limitations:
- Domain-based heuristics only; does not verify factual accuracy
- Cannot detect sophisticated misinformation on trusted domains
- Date parsing relies on common formats; may miss unusual ones
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
from urllib.parse import urlparse
from datetime import datetime, timezone
import re


# ── Domain authority database ────────────────────────────────────────────

AUTHORITY_TIERS = {
    # Tier 1: Highest trust (score 9-10)
    "high": {
        "suffixes": [".gov", ".edu", ".mil"],
        "domains": [
            "nature.com", "science.org", "thelancet.com", "nejm.org",
            "ieee.org", "acm.org", "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
            "who.int", "cdc.gov", "nih.gov", "un.org",
        ],
        "score": 9,
    },
    # Tier 2: Established outlets (score 7-8)
    "medium": {
        "suffixes": [".org"],
        "domains": [
            "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
            "nytimes.com", "washingtonpost.com", "theguardian.com",
            "economist.com", "bloomberg.com", "wsj.com",
            "techcrunch.com", "arstechnica.com", "wired.com",
            "stackoverflow.com", "github.com",
        ],
        "score": 7,
    },
    # Tier 3: General web (score 4-5)
    "low": {
        "domains": [
            "medium.com", "substack.com", "wordpress.com",
            "blogspot.com", "quora.com", "reddit.com",
        ],
        "score": 4,
    },
}


class CredibilityInput(BaseModel):
    """Input schema for Source Credibility Scorer."""
    url: str = Field(
        description="The URL of the source to evaluate."
    )
    publication_date: Optional[str] = Field(
        default=None,
        description="Publication date in ISO format (YYYY-MM-DD), if known."
    )
    has_author: Optional[bool] = Field(
        default=None,
        description="Whether the source has a named author."
    )
    has_citations: Optional[bool] = Field(
        default=None,
        description="Whether the source includes references or citations."
    )


class SourceCredibilityScorer(BaseTool):
    """Scores the credibility of a web source on a 1-10 scale."""

    name: str = "Source Credibility Scorer"
    description: str = (
        "Evaluates the credibility of a web source based on domain authority, "
        "content freshness, author attribution, and citation presence. "
        "Returns a score from 1 (unreliable) to 10 (highly credible) "
        "with a detailed breakdown."
    )
    args_schema: type[BaseModel] = CredibilityInput

    def _run(
        self,
        url: str,
        publication_date: Optional[str] = None,
        has_author: Optional[bool] = None,
        has_citations: Optional[bool] = None,
    ) -> str:
        """Execute credibility evaluation."""

        scores = {}

        # ── 1. Domain authority (0-10) ───────────────────────────────
        domain_score, domain_detail = self._score_domain(url)
        scores["domain_authority"] = {
            "score": domain_score,
            "detail": domain_detail,
            "weight": 0.40,
        }

        # ── 2. Content freshness (0-10) ──────────────────────────────
        freshness_score, freshness_detail = self._score_freshness(publication_date)
        scores["content_freshness"] = {
            "score": freshness_score,
            "detail": freshness_detail,
            "weight": 0.25,
        }

        # ── 3. Author attribution (0-10) ─────────────────────────────
        author_score, author_detail = self._score_author(has_author)
        scores["author_attribution"] = {
            "score": author_score,
            "detail": author_detail,
            "weight": 0.15,
        }

        # ── 4. Citation presence (0-10) ──────────────────────────────
        citation_score, citation_detail = self._score_citations(has_citations)
        scores["citation_presence"] = {
            "score": citation_score,
            "detail": citation_detail,
            "weight": 0.20,
        }

        # ── Weighted total ───────────────────────────────────────────
        total = sum(
            s["score"] * s["weight"] for s in scores.values()
        )
        total = round(min(max(total, 1.0), 10.0), 1)

        # ── Recommendation ───────────────────────────────────────────
        if total >= 8:
            recommendation = "HIGHLY CREDIBLE — suitable as a primary source."
        elif total >= 6:
            recommendation = "MODERATELY CREDIBLE — use with cross-referencing."
        elif total >= 4:
            recommendation = "LOW CREDIBILITY — verify claims independently."
        else:
            recommendation = "UNRELIABLE — avoid citing without strong corroboration."

        # ── Format output ────────────────────────────────────────────
        report_lines = [
            f"Source Credibility Report",
            f"URL: {url}",
            f"Overall Score: {total}/10 — {recommendation}",
            f"",
            f"Breakdown:",
        ]
        for factor, data in scores.items():
            label = factor.replace("_", " ").title()
            report_lines.append(
                f"  {label}: {data['score']}/10 "
                f"(weight {data['weight']:.0%}) — {data['detail']}"
            )

        return "\n".join(report_lines)

    # ── Scoring helpers ──────────────────────────────────────────────

    def _score_domain(self, url: str) -> tuple[float, str]:
        """Score based on domain reputation."""
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            hostname = parsed.hostname or ""
        except Exception:
            return 3.0, "Could not parse URL"

        # Check each tier
        for tier_name, tier in AUTHORITY_TIERS.items():
            # Check exact domain matches
            for domain in tier["domains"]:
                if hostname == domain or hostname.endswith(f".{domain}"):
                    return float(tier["score"]), f"{hostname} — {tier_name} authority domain"
            # Check suffix matches
            for suffix in tier.get("suffixes", []):
                if hostname.endswith(suffix):
                    return float(tier["score"]), f"{hostname} — {suffix} domain"

        # HTTPS bonus
        is_https = parsed.scheme == "https"
        base = 5.0 if is_https else 3.0
        detail = f"{hostname} — unranked domain"
        if not is_https:
            detail += " (no HTTPS)"
        return base, detail

    def _score_freshness(self, pub_date: Optional[str]) -> tuple[float, str]:
        """Score based on how recent the content is."""
        if not pub_date:
            return 5.0, "No publication date provided — neutral score"

        try:
            # Try common date formats
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%B %d, %Y"):
                try:
                    dt = datetime.strptime(pub_date, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                return 5.0, f"Could not parse date: {pub_date}"

            now = datetime.now(timezone.utc)
            days_old = (now - dt).days

            if days_old < 0:
                return 5.0, "Future date — suspicious"
            elif days_old <= 90:
                return 9.0, f"Published {days_old} days ago — very recent"
            elif days_old <= 365:
                return 7.0, f"Published {days_old} days ago — recent"
            elif days_old <= 730:
                return 5.0, f"Published {days_old} days ago — somewhat dated"
            else:
                years = days_old // 365
                return 3.0, f"Published ~{years} years ago — potentially outdated"

        except Exception as e:
            return 5.0, f"Date evaluation error: {e}"

    def _score_author(self, has_author: Optional[bool]) -> tuple[float, str]:
        """Score based on author attribution."""
        if has_author is None:
            return 5.0, "Author attribution unknown — neutral score"
        if has_author:
            return 8.0, "Named author present — accountable source"
        return 3.0, "No named author — reduced accountability"

    def _score_citations(self, has_citations: Optional[bool]) -> tuple[float, str]:
        """Score based on citation/reference presence."""
        if has_citations is None:
            return 5.0, "Citation presence unknown — neutral score"
        if has_citations:
            return 9.0, "Contains references/citations — verifiable claims"
        return 3.0, "No citations or references — unverifiable claims"
