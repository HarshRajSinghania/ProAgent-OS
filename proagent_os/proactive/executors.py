"""Safe recommendation executors.

The webhook target is the operator URL from settings. The recommendation
``action`` payload is JSON data in the body. It is never used as a URL,
shell command, or code path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

import httpx

from proagent_os.config import Settings, get_settings

logger = logging.getLogger("proagent.executors")


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    mode: str
    error: Optional[str] = None

    def as_api(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": self.ok, "mode": self.mode}
        if self.error:
            payload["error"] = self.error
        return payload


class RecommendationExecutor(Protocol):
    mode: str

    def execute(self, recommendation: Dict[str, Any]) -> ExecutionResult:
        """Run the executor against a recommendation row (action_payload already decoded)."""


class NoopExecutor:
    """Acknowledge execution locally. No network and no use of the action payload."""

    mode = "noop"

    def execute(self, recommendation: Dict[str, Any]) -> ExecutionResult:
        logger.info(
            "noop executor acknowledged recommendation %s tenant %s",
            recommendation.get("id"),
            recommendation.get("tenant_id"),
        )
        return ExecutionResult(ok=True, mode=self.mode)


class WebhookExecutor:
    """POST a fixed JSON body to the operator-configured URL."""

    mode = "webhook"

    def __init__(self, url: str, timeout_s: float, token: str = "") -> None:
        self.url = _require_http_url(url)
        self.timeout_s = timeout_s
        self.token = token.strip()

    def execute(self, recommendation: Dict[str, Any]) -> ExecutionResult:
        action = recommendation.get("action_payload")
        if not isinstance(action, dict):
            action = {}
        body = {
            "recommendation_id": recommendation.get("id"),
            "tenant_id": recommendation.get("tenant_id"),
            "title": recommendation.get("title") or "",
            "rationale": recommendation.get("rationale") or "",
            "action": action,
            "decided_at": recommendation.get("decided_at"),
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        # URL, timeout, and token come from this instance (settings). Nothing in
        # `body` is consulted for the request target. Redirects and env proxies
        # are disabled so the POST cannot be bounced off the configured host.
        try:
            with httpx.Client(
                timeout=self.timeout_s,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(self.url, json=body, headers=headers)
        except httpx.HTTPError:
            logger.warning(
                "webhook executor request failed for recommendation %s",
                recommendation.get("id"),
            )
            return ExecutionResult(ok=False, mode=self.mode, error="webhook request failed")
        if not response.is_success:
            logger.warning(
                "webhook executor non-success status %s for recommendation %s",
                response.status_code,
                recommendation.get("id"),
            )
            return ExecutionResult(
                ok=False,
                mode=self.mode,
                error=f"webhook returned HTTP {response.status_code}",
            )
        logger.info(
            "webhook executor delivered recommendation %s status %s",
            recommendation.get("id"),
            response.status_code,
        )
        return ExecutionResult(ok=True, mode=self.mode)


def build_executor(settings: Optional[Settings] = None) -> RecommendationExecutor:
    """Build the executor selected by settings. `off` is not an executor."""
    settings = settings or get_settings()
    mode = settings.executor_mode
    if mode == "noop":
        return NoopExecutor()
    if mode == "webhook":
        return WebhookExecutor(
            url=settings.executor_webhook_url,
            timeout_s=settings.executor_webhook_timeout_s,
            token=settings.executor_webhook_token,
        )
    raise ValueError(f"no executor for mode {mode}")


def _require_http_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("PROAGENT_EXECUTOR_WEBHOOK_URL is required when executor mode is webhook")
    try:
        parsed = httpx.URL(cleaned)
    except httpx.InvalidURL:
        raise ValueError("PROAGENT_EXECUTOR_WEBHOOK_URL must be an absolute http(s) URL") from None
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise ValueError("PROAGENT_EXECUTOR_WEBHOOK_URL must be an absolute http(s) URL")
    return str(parsed)
