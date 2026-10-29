"""Support desk vertical: registry, keyword skills, KB search, follow-up monitor."""
from __future__ import annotations

from pathlib import Path

import pytest

from proagent_os.db import get_db, new_id, utcnow
from proagent_os.harness.registry import AgentRegistry
from proagent_os.services import get_services

FIXTURES = Path("verticals/support_desk/fixtures")
REFUND_TICKET = (
    "Subject: Refund for last month\n"
    "I was charged on October 1 and want a refund. Invoice NW-1044."
)


def _tenant() -> str:
    tid = new_id("ten")
    get_db().insert(
        "tenants",
        {
            "id": tid,
            "name": "Northwind Support",
            "api_key": new_id("pk"),
            "goals": "Answer from published support policy",
            "constraints": "Do not invent refund windows",
            "tone": "concise",
            "created_at": utcnow(),
        },
    )
    return tid


def test_support_desk_agent_and_skills_load():
    reg = AgentRegistry(Path("config/agents.yaml"))
    reg.merge_tree(Path("verticals"))
    merged = reg.get("support_triage")
    assert merged is not None
    assert merged.role == "specialist"
    assert merged.tools == ["kb_search", "emit_recommendation", "clock"]
    assert "knowledge base" in merged.system_prompt.lower()
    assert reg.get("market_scout") is not None

    svc = get_services()
    agent = svc.agents.get("support_triage")
    assert agent is not None and agent.tools == merged.tools
    triage = svc.skills.get("ticket_triage")
    lookup = svc.skills.get("policy_lookup")
    assert triage is not None and triage.runner is not None
    assert lookup is not None and lookup.runner is not None
    assert svc.skills.get("market_scan") is not None
    assert len(list(FIXTURES.glob("*.md"))) == 3


def test_ticket_triage_cites_policies_and_honors_passages():
    triage = get_services().skills.get("ticket_triage")
    lookup = get_services().skills.get("policy_lookup")
    assert triage is not None and triage.runner is not None
    assert lookup is not None and lookup.runner is not None

    refund = triage.runner(tenant_id="ten_demo", ticket=REFUND_TICKET)
    assert refund["priority"] == "high"
    assert refund["category"] == "billing"
    assert refund["needs_human"] is False
    assert refund["citations"][0]["title"] == "Refund Policy"
    assert "30 days" in refund["citations"][0]["excerpt"]
    assert "Refund Policy" in refund["follow_up"]

    locked = triage.runner(ticket="The customer is locked out and cannot log in after five failed sign-ins.")
    assert locked["category"] == "access"
    assert locked["priority"] == "urgent"
    assert locked["needs_human"] is True
    assert locked["citations"][0]["title"] == "Account Access FAQ"

    outage = triage.runner(ticket="Production API is down. This is a service outage.")
    assert outage["category"] == "outage"
    assert outage["priority"] == "urgent"
    assert outage["citations"][0]["title"] == "First Response SLA"

    unknown = triage.runner(ticket="Where is the printed user guide?")
    assert unknown["category"] == "general"
    assert unknown["priority"] == "normal"
    assert unknown["citations"] == []
    assert unknown["needs_human"] is True

    blocked = triage.runner(
        ticket="Please refund invoice 9",
        passages=[{"title": "Shipping", "source": "ship.md", "content": "Shipping takes five business days."}],
    )
    assert blocked["category"] == "billing"
    assert blocked["priority"] == "high"
    assert blocked["citations"] == []
    assert blocked["needs_human"] is True

    quoted = lookup.runner(query="service outage product is down")
    assert quoted["citations"][0]["title"] == "First Response SLA"
    assert "outage" in quoted["citations"][0]["excerpt"].lower()
    assert lookup.runner(query="office snack menu")["citations"] == []
    assert lookup.runner(query="")["citations"] == []


@pytest.mark.asyncio
async def test_support_desk_ingest_search_task_and_follow_up():
    tid = _tenant()
    svc = get_services()
    paths = sorted(FIXTURES.glob("*.md"))
    assert [p.name for p in paths] == [
        "account_access_faq.md",
        "refund_policy.md",
        "sla_first_response.md",
    ]
    for path in paths:
        meta = svc.kb.ingest_file(tid, path)
        assert meta["chunks"] >= 1
        assert meta["title"] == path.stem

    hits = svc.kb.search(tid, "refund within 30 days", top_k=3)
    assert hits
    assert hits[0]["title"] == "refund_policy"
    assert "30 days" in hits[0]["content"]

    triage = svc.skills.get("ticket_triage").runner(tenant_id=tid, ticket=REFUND_TICKET, passages=hits)
    assert triage["citations"][0]["title"] == "Refund Policy"
    assert "30 days" in triage["citations"][0]["excerpt"]

    task = await svc.orchestrator.run_task(
        tid,
        "A customer wants a refund for invoice NW-1044 charged 10 days ago. What should support tell them?",
    )
    assert task["status"] == "completed"
    assert task["result"]
    assert [step.get("agent") for step in task["plan"]["steps"]] == ["researcher", "analyst"]

    mon = svc.monitors.create(
        tid,
        name="Refund follow-up",
        kind="data_source",
        config={
            "query": "refund within 30 days",
            "title": "Follow up: refund request matches the 30-day policy",
        },
        interval_seconds=3600,
    )
    run = await svc.monitors.run_once(tid, mon["id"])
    rec = run["recommendation"]
    assert rec["status"] == "pending"
    assert rec["title"] == "Follow up: refund request matches the 30-day policy"
    assert rec["action_payload"]["type"] == "follow_up"
    assert "30 days" in rec["rationale"]
    decided = svc.recommendations.decide(tid, rec["id"], "approved")
    assert decided["status"] == "executed"
    assert decided["execution"] == {"ok": True, "mode": "noop"}
