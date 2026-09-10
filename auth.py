"""API key check for the endpoints that cost money to serve.

A research run makes about fifteen model calls. The provider's free tier allows
twenty per day, so one stranger submitting one job exhausts the quota for
everyone, including a live demo an hour later. An open endpoint in front of a
metered upstream hands the bill to whoever finds the URL.

The key is read from the environment. When API_KEY is unset the check passes,
which keeps local runs and the test suite from needing configuration; the
deployed service sets it. /health stays open deliberately: App Runner polls it
every twenty seconds to decide whether the instance is alive, and a 401 there
would get the container killed and restarted.
"""

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

HEADER_NAME = "X-API-Key"

# Declared to FastAPI so /docs renders an Authorize button. auto_error is off
# because a missing key has to reach our own check, which decides whether the
# service is running in open mode.
_scheme = APIKeyHeader(name=HEADER_NAME, auto_error=False)


def _configured_key() -> str:
    """Read at call time, not import, so tests can set it per case."""
    return os.getenv("API_KEY", "")


def require_api_key(presented: str = Security(_scheme)) -> None:
    """Reject the request unless the caller presented the configured key."""
    expected = _configured_key()
    if not expected:
        return
    # Constant-time: a plain == returns early on the first wrong character,
    # which leaks how much of a guess was correct.
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail=f"missing or invalid {HEADER_NAME}",
        )
