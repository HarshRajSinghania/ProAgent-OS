from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import httpx

from proagent_os.db import dumps, get_db, new_id, utcnow
from proagent_os.professional.kb.store import KnowledgeBase
from proagent_os.professional.tools.base import Tool, ToolContext, ToolRegistry, ToolResult


class HttpFetchTool(Tool):
    name = "http_fetch"
    description = "Fetch a public HTTP(S) URL and return truncated text content."

    async def run(self, arguments: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = arguments.get("url")
        if not url:
            return ToolResult(ok=False, output=None, error="url required")
        # Local fixture scheme for offline demos
        if url.startswith("fixture://"):
            name = url.replace("fixture://", "")
            path = Path("fixtures") / name
            if not path.exists():
                return ToolResult(ok=False, output=None, error=f"fixture not found: {name}")
            text = path.read_text(encoding="utf-8")
            return ToolResult(ok=True, output={"url": url, "status": 200, "text": text[:8000]})
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "ProAgentOS/0.1"})
            text = resp.text[:8000]
            return ToolResult(ok=True, output={"url": url, "status": resp.status_code, "text": text})


class FileReadTool(Tool):
    name = "file_read"
    description = "Read a local text/markdown file under fixtures/ or data/ (sandboxed)."

    async def run(self, arguments: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        path_str = arguments.get("path", "")
        path = Path(path_str)
        allowed_roots = [Path("fixtures").resolve(), Path("data").resolve(), Path("skills").resolve()]
        try:
            resolved = path.resolve()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, output=None, error=str(exc))
        if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
            return ToolResult(ok=False, output=None, error="path outside allowed roots")
        if not resolved.exists() or not resolved.is_file():
            return ToolResult(ok=False, output=None, error="file not found")
        if resolved.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html"}:
            return ToolResult(ok=False, output=None, error="unsupported file type")
        return ToolResult(ok=True, output={"path": str(path), "content": resolved.read_text(encoding="utf-8")[:20000]})


class KbSearchTool(Tool):
    name = "kb_search"
    description = "Search the tenant knowledge base with keyword/BM25-style retrieval."

    async def run(self, arguments: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = arguments.get("query", "")
        top_k = int(arguments.get("top_k", 5))
        kb = KnowledgeBase()
        hits = kb.search(ctx.tenant_id, query, top_k=top_k)
        return ToolResult(ok=True, output={"query": query, "hits": hits})


class ClockTool(Tool):
    name = "clock"
    description = "Return the current UTC timestamp."

    async def run(self, arguments: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        now = datetime.now(timezone.utc)
        return ToolResult(
            ok=True,
            output={"utc": now.isoformat(), "unix": int(now.timestamp()), "timezone": "UTC"},
        )


class EmitRecommendationTool(Tool):
    name = "emit_recommendation"
    description = "Propose an actionable recommendation for human-in-the-loop approval."

    async def run(self, arguments: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        title = arguments.get("title") or "Untitled recommendation"
        rationale = arguments.get("rationale") or ""
        action = arguments.get("action") or {}
        rec_id = new_id("rec")
        get_db().insert(
            "recommendations",
            {
                "id": rec_id,
                "tenant_id": ctx.tenant_id,
                "monitor_id": ctx.monitor_id,
                "task_id": ctx.task_id,
                "title": title,
                "rationale": rationale,
                "action_payload_json": dumps(action),
                "status": "pending",
                "created_at": utcnow(),
                "decided_at": None,
            },
        )
        return ToolResult(ok=True, output={"recommendation_id": rec_id, "status": "pending", "title": title})


def build_builtin_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (HttpFetchTool(), FileReadTool(), KbSearchTool(), ClockTool(), EmitRecommendationTool()):
        registry.register(tool)
    return registry
