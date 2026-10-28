from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from proagent_os.db import get_db, new_id, utcnow
from proagent_os.llm.base import LLMMessage, ToolCall
from proagent_os.llm.mock import MockLLMProvider
from proagent_os.llm.openai_compat import OpenAICompatProvider
from proagent_os.services import get_services


def _tenant() -> str:
    tid = new_id("ten")
    get_db().insert(
        "tenants",
        {
            "id": tid,
            "name": "Tool Loop Co",
            "api_key": "pk_tools",
            "goals": "Test tools",
            "constraints": "",
            "tone": "professional",
            "created_at": utcnow(),
        },
    )
    return tid


@pytest.mark.asyncio
async def test_mock_orchestrator_multi_tool_rounds():
    """MockLLM + orchestrator executes ≥2 tool rounds then finishes."""
    tid = _tenant()
    svc = get_services()
    svc.kb.ingest_text(
        tid,
        "manual",
        "Product",
        "Acme conversion rate is below target at 1.8 percent. Activation is the lever.",
    )
    result = await svc.orchestrator.run_task(
        tid, "Why is conversion low and what should we do?"
    )
    assert result["status"] == "completed"
    tool_events = [t for t in result["trace"] if t.get("phase") == "tool"]
    assert len(tool_events) >= 2, f"expected ≥2 tool rounds, got {len(tool_events)}: {tool_events}"
    assert all("id" in t and "name" in t and "latency_ms" in t for t in tool_events)
    assert any(t["phase"] == "aggregate" for t in result["trace"])
    assert result["result"]


@pytest.mark.asyncio
async def test_mock_provider_returns_structured_tool_calls():
    llm = MockLLMProvider()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "kb_search",
                "description": "search",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clock",
                "description": "time",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
    messages = [
        LLMMessage(role="system", content="You are the Researcher specialist. Use tools."),
        LLMMessage(role="user", content="Task: find conversion facts\nYour goal: gather evidence"),
    ]
    r1 = await llm.chat(messages, tools=tools, tool_choice="auto")
    assert r1.tool_calls
    assert r1.tool_calls[0].name == "kb_search"
    assert r1.content is None

    messages.append(LLMMessage(role="assistant", content=None, tool_calls=r1.tool_calls))
    messages.append(
        LLMMessage(
            role="tool",
            content=json.dumps({"ok": True, "output": {"hits": []}}),
            tool_call_id=r1.tool_calls[0].id,
            name="kb_search",
        )
    )
    r2 = await llm.chat(messages, tools=tools)
    assert r2.tool_calls
    assert r2.tool_calls[0].name == "clock"

    messages.append(LLMMessage(role="assistant", content=None, tool_calls=r2.tool_calls))
    messages.append(
        LLMMessage(
            role="tool",
            content=json.dumps({"ok": True, "output": {"utc": "now"}}),
            tool_call_id=r2.tool_calls[0].id,
            name="clock",
        )
    )
    r3 = await llm.chat(messages, tools=tools)
    assert not r3.tool_calls
    assert r3.content


@pytest.mark.asyncio
async def test_openai_compat_payload_includes_tools(monkeypatch):
    """OpenAICompatProvider includes tools/tool_choice in the HTTP payload."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content.decode())
        body = {
            "id": "chatcmpl-test",
            "model": "gpt-test",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "clock",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatProvider(
        base_url="https://example.test/v1",
        api_key="sk-test-not-real",
        model="gpt-test",
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "clock",
                "description": "time",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    with patch("proagent_os.llm.openai_compat.httpx.AsyncClient", side_effect=client_factory):
        resp = await provider.chat(
            [LLMMessage(role="user", content="What time is it?")],
            tools=tools,
            tool_choice="auto",
        )

    assert "tools" in captured["json"]
    assert captured["json"]["tools"] == tools
    assert captured["json"]["tool_choice"] == "auto"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "clock"
    assert resp.tool_calls[0].id == "call_abc"
    assert resp.content is None
