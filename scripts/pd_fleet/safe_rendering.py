"""Small helpers for rendering attacker-controlled values at observability boundaries."""
from __future__ import annotations

from typing import Any

UNSUPPORTED_TYPE = "[UNSUPPORTED TYPE]"
RUNTIME_ERROR = "[RUNTIME ERROR]"
PARALLEL_ERROR = "[PARALLEL ERROR]"
PROVIDER_ERROR = "[PROVIDER ERROR]"


def safe_text(value: Any, marker: str, *, limit: int | None = None) -> str:
    """Render exact strings only, escaping controls and bounding the result."""
    if type(value) is not str:
        return marker
    rendered = "".join(
        char if 32 <= ord(char) < 127 or char in "\n\t"
        else f"\\x{ord(char):02x}"
        for char in value
    )
    return rendered if limit is None else rendered[:limit]