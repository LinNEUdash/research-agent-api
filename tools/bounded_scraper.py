"""A scraper that will not hand an unbounded page body to the model.

The stock ScrapeWebsiteTool returns every character it finds, boilerplate
included. That is fine on a short article and ruinous on a long government or
report page: one scrape can be several hundred thousand characters, and the
task chain sends it downstream twice more as context.

The Gemini free tier caps input at 250,000 tokens per minute. A single
oversized scrape is enough to exceed it, which is what failed job
95093704-4a12-417b-916e-9f4178f7dbf4 five minutes into a run. Capping requests
per minute does not help, because the limit being hit is measured in tokens,
not calls.

Truncation is visible rather than silent: the model is told the page was cut
short, so it can say the source was only partially read instead of treating a
fragment as the whole document.
"""

from crewai_tools import ScrapeWebsiteTool

from config.settings import MAX_SCRAPE_CHARS

NOTICE = (
    "\n\n[Truncated after {limit} characters. This page was longer than the "
    "scrape limit; treat it as a partial read of the source.]"
)


class BoundedScrapeWebsiteTool(ScrapeWebsiteTool):
    """ScrapeWebsiteTool with a ceiling on how much text it returns."""

    def _run(self, **kwargs) -> str:
        text = super()._run(**kwargs)
        if not isinstance(text, str):
            return text
        if len(text) <= MAX_SCRAPE_CHARS:
            return text
        return text[:MAX_SCRAPE_CHARS] + NOTICE.format(limit=MAX_SCRAPE_CHARS)
