"""Application settings loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
