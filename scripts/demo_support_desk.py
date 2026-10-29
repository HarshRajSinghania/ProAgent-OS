#!/usr/bin/env python3
"""Support desk demo: tenant, policy ingest, search, triage skill, mock task, follow-up.

Offline. No API key. Approve uses the default noop executor (status executed, no network, no customer reply).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PROAGENT_DB_PATH", str(ROOT / "data" / "demo_support_desk.db"))
os.environ.setdefault("PROAGENT_ADMIN_KEY", "dev-admin-key")
os.environ.setdefault("PROAGENT_LLM_PROVIDER", "mock")
os.environ.setdefault("PROAGENT_EXECUTOR_MODE", "noop")
os.environ.setdefault("PROAGENT_EXECUTOR_ON_APPROVE", "true")
os.environ.setdefault("PROAGENT_AGENTS_CONFIG", str(ROOT / "config" / "agents.yaml"))


def _ensure_support_skills() -> None:
    """Keep any caller-provided dirs and always include this pack."""
    extra = str(ROOT / "verticals" / "support_desk" / "skills")
    current = os.environ.get("PROAGENT_SKILLS_DIRS", "")
    if current.strip():
        parts = [p.strip() for p in current.split(",") if p.strip()]
    else:
        parts = [
            str(ROOT / "skills"),
            str(ROOT / "verticals" / "example" / "skills"),
        ]
    if extra not in parts:
        parts.append(extra)
    os.environ["PROAGENT_SKILLS_DIRS"] = ",".join(parts)


_ensure_support_skills()

FIXTURES = ROOT / "verticals" / "support_desk" / "fixtures"
REFUND_TICKET = (
    "Subject: Refund for last month\n"
    "I was charged on October 1 and want a refund. Invoice NW-1044."
)


async def main() -> None:
    from proagent_os.config import get_settings
    from proagent_os.db import get_db, new_id, reset_db, utcnow
    from proagent_os.llm.factory import reset_llm_cache
    from proagent_os.services import reset_services

    get_settings.cache_clear()
    reset_llm_cache()
    db_path = Path(os.environ["PROAGENT_DB_PATH"])
    if db_path.exists():
        db_path.unlink()
    reset_db(db_path)
    svc = reset_services()

    print("=== ProAgent OS Support Desk Demo ===\n")

    agent_ids = [a.id for a in svc.agents.list()]
    skill_ids = [s.id for s in svc.skills.list()]
    if "support_triage" not in agent_ids:
        raise SystemExit(f"support_triage was not merged from verticals/*/agents. agents={agent_ids}")
    if "ticket_triage" not in skill_ids or "policy_lookup" not in skill_ids:
        raise SystemExit(f"support desk skills missing. skills={skill_ids}")
    print(f"agents: {agent_ids}")
    print(f"skills: {skill_ids}\n")

    tid = new_id("ten")
    api_key = "pk_demo_northwind_support"
    get_db().insert(
        "tenants",
        {
            "id": tid,
            "name": "Northwind Support",
            "api_key": api_key,
            "goals": "Answer from published support policy and escalate exceptions",
            "constraints": "Do not invent refund windows or send a reply without approval",
            "tone": "concise and cite the policy",
            "created_at": utcnow(),
        },
    )
    print(f"[1] Tenant created: id={tid} api_key={api_key}")

    docs = []
    for path in sorted(FIXTURES.glob("*.md")):
        docs.append(svc.kb.ingest_file(tid, path))
    print("[2] Ingested policies: " + ", ".join(f"{d['title']} ({d['chunks']} chunks)" for d in docs))
    if len(docs) != 3:
        raise SystemExit(f"expected 3 fixtures, ingested {len(docs)}")

    hits = svc.kb.search(tid, "refund within 30 days", top_k=3)
    if not hits or hits[0]["title"] != "refund_policy":
        raise SystemExit(f"expected refund_policy as the top hit, got {hits[:1]}")
    print(f"    Search 'refund within 30 days' → {len(hits)} hits; top={hits[0]['title']} score={hits[0]['score']}")

    triage = svc.skills.get("ticket_triage").runner(tenant_id=tid, ticket=REFUND_TICKET, passages=hits)
    lookup = svc.skills.get("policy_lookup").runner(tenant_id=tid, query="refund within 30 days", passages=hits)
    if triage["priority"] != "high" or triage["category"] != "billing":
        raise SystemExit(f"unexpected triage labels: {triage}")
    if not triage["citations"] or triage["citations"][0]["title"] != "Refund Policy":
        raise SystemExit(f"expected Refund Policy citation, got {triage['citations']}")
    if not lookup["citations"] or lookup["citations"][0]["title"] != "Refund Policy":
        raise SystemExit(f"expected policy lookup to cite Refund Policy, got {lookup['citations']}")
    print(
        f"[3] ticket_triage → {triage['priority']} / {triage['category']}; "
        f"cite {triage['citations'][0]['title']}"
    )
    print(f"    {triage['citations'][0]['excerpt']}")
    print(f"    follow_up: {triage['follow_up']}")
    print(f"    policy_lookup → {lookup['citations'][0]['title']}")

    task = await svc.orchestrator.run_task(
        tid,
        "A customer wants a refund for invoice NW-1044 charged 10 days ago. What should support tell them?",
    )
    if task["status"] != "completed":
        raise SystemExit(f"task did not complete: {task['status']}")
    steps = [s.get("agent") for s in task["plan"].get("steps", [])]
    print(f"[4] Mock task {task['task_id']} status={task['status']} plan={steps}")
    print("    Mock planner assigns researcher then analyst. support_triage is registered for a real model.")

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
    rec = run.get("recommendation") or {}
    if rec.get("title") != "Follow up: refund request matches the 30-day policy":
        raise SystemExit(f"monitor did not propose the follow-up: {run}")
    print(f"[5] Monitor {mon['id']} proposed {rec['id']}: {rec['title']} ({rec['status']})")

    approved = svc.recommendations.decide(tid, rec["id"], "approved")
    execution = approved.get("execution") or {}
    if approved.get("status") != "executed" or execution.get("mode") != "noop" or execution.get("ok") is not True:
        raise SystemExit(f"expected noop executor to mark executed, got {approved}")
    print(
        f"[6] Recommendation status → {approved['status']}"
        f" (executor {execution.get('mode')}, ok={execution.get('ok')}; no customer reply is sent)"
    )

    outcome = svc.metrics.record_outcome(tid, rec["id"], "followups_reviewed", 1, {"note": "demo only"})
    learning = svc.learning.apply_outcome_feedback(
        tid, rec["id"], "followups_reviewed", 1, skill_id="ticket_triage", success_threshold=0.0
    )
    print(f"    Outcome {outcome['metric_name']}={outcome['value']}; skill weight {learning['skill_weight']}")
    print(
        "\nDemo complete. Keyword triage. Noop executor marks the follow-up executed"
        " and does not send a reply. Not a production helpdesk."
    )
    print(f"Use Authorization: Bearer {api_key}")


if __name__ == "__main__":
    asyncio.run(main())
