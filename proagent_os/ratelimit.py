"""In-process fixed-window rate limit for /api/v1.

One bucket per live tenant id. The admin key and unrecognized bearers
(including revoked secrets) use their own buckets. Counters live in this
process only: a restart or a second worker does not share them. Redis is
not required.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from proagent_os.auth import extract_bearer
from proagent_os.config import get_settings
from proagent_os.db import get_db
from proagent_os.keys import key_usable

logger = logging.getLogger("proagent.ratelimit")

RATE_LIMIT_DETAIL = "Rate limit exceeded"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()

    def hit(self, identity: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = time.time()
        window = max(1, int(window_seconds))
        slot = int(now // window)
        with self._lock:
            stale = [key for key in self._counts if key[1] != slot]
            for key in stale:
                del self._counts[key]
            bucket = (identity, slot)
            count = self._counts.get(bucket, 0) + 1
            self._counts[bucket] = count
        remaining = max(0, limit - count)
        retry_after = window - int(now % window)
        if retry_after < 1:
            retry_after = 1
        allowed = count <= limit
        return RateLimitDecision(
            allowed=allowed,
            limit=limit,
            remaining=remaining if allowed else 0,
            retry_after=retry_after,
        )


_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> InMemoryRateLimiter:
    return _limiter


def reset_rate_limiter() -> None:
    _limiter.reset()


def rate_limit_identity(authorization: str | None) -> str:
    token = extract_bearer(authorization)
    if token is None:
        return "anonymous"
    settings = get_settings()
    if token == settings.admin_key:
        return "admin"
    row = get_db().fetchone(
        "SELECT id, api_key, key_status FROM tenants WHERE api_key = ?",
        (token,),
    )
    if row and key_usable(row):
        return f"tenant:{row['id']}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    return f"key:{digest}"


def _limited_response(decision: RateLimitDecision) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": RATE_LIMIT_DETAIL},
        headers={
            "Retry-After": str(decision.retry_after),
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": "0",
        },
    )


async def enforce_rate_limit(request: Request, call_next):
    path = request.url.path
    if path != "/api/v1" and not path.startswith("/api/v1/"):
        return await call_next(request)
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return await call_next(request)
    identity = rate_limit_identity(request.headers.get("authorization"))
    decision = get_rate_limiter().hit(
        identity,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if not decision.allowed:
        logger.info(
            "rate_limit exceeded identity=%s limit=%s window_seconds=%s",
            identity,
            decision.limit,
            settings.rate_limit_window_seconds,
        )
        return _limited_response(decision)
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    return response
