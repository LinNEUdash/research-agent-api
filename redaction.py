"""Strips credentials out of text before it is logged or returned to a caller.

The Gemini endpoint authenticates with a `key` query parameter rather than a
header, so the API key ends up inside the request URL. Any HTTP error therefore
carries the key in its message, and that message travels two ways it should
not: into the job record returned by GET /jobs/{id}, and into stdout, which
App Runner forwards to CloudWatch Logs where it would persist.

Everything that leaves this service passes through redact() first.
"""

import re

PLACEHOLDER = "[REDACTED]"

_PATTERNS = [
    # ?key=... or &api_key=... in a URL
    re.compile(r"(?i)([?&](?:key|api[_-]?key|access[_-]?token|token)=)[^&\s\"']+"),
    # Authorization: Bearer <token>
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    # Bare provider key formats that may appear outside a URL
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[0-9A-Za-z_\-]{20,}"),
]


def redact(text: str) -> str:
    """Return text with any credential-looking substring replaced."""
    if not text:
        return text

    result = text
    for pattern in _PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda m: m.group(1) + PLACEHOLDER, result)
        else:
            result = pattern.sub(PLACEHOLDER, result)
    return result
