"""Application settings loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")

# Longest page body a scrape may contribute to a prompt, in characters.
# Kept in the environment so the ceiling can be raised on a paid quota without
# a rebuild. See tools.bounded_scraper for why there is a ceiling at all.
MAX_SCRAPE_CHARS = int(os.getenv("MAX_SCRAPE_CHARS", "15000"))

# Retries litellm performs on a failed model call. Covers a brief spike; a
# quota that stays exhausted for a full minute still fails the job.
LLM_NUM_RETRIES = int(os.getenv("LLM_NUM_RETRIES", "3"))
