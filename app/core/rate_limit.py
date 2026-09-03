"""Rate limiter for the authentication endpoints (slowapi, per-IP).

In-memory storage — appropriate for the single-process development/demo
deployment this project targets. A multi-worker production setup would
need a shared backend (Redis), out of scope here.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
