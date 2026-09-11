"""Shared test setup.

`config.settings` calls load_dotenv() at import, so a developer's .env leaks
into os.environ for the whole test session. Once API_KEY was added to a local
.env, every request the test client made started coming back 401 — on that
machine only. CI has no .env, so the suite stayed green there and failed
locally, which is the wrong way round for a signal to break.

Tests that care about the key set it themselves. Everything else runs with it
cleared, so the result does not depend on which machine is running it.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    yield
