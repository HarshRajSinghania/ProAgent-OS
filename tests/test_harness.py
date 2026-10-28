from __future__ import annotations

import pytest

from proagent_os.db import get_db, new_id, utcnow
from proagent_os.services import get_services


def _tenant() -> str:
    tid = new_id("ten")
    get_db().insert(
        "tenants",
        {
            "id": tid,
            "name": "Test Co",
            "api_key": "pk_test",
            "goals": "Grow efficiently",
            "constraints": "Stay compliant",
            "tone": "professional",
            "created_at": utcnow(),
        },
    )
    return tid


@pytest.mark.asyncio
async def test_plan_loop_completes():
    tid = _tenant()
    svc = get_services()
    # Seed KB so researcher has something to find
    svc.kb.ingest_text(tid, "manual", "Product", "Acme conversion rate is below target at 1.8 percent.")
    result = await svc.orchestrator.run_task(tid, "Why is conversion low and what should we do?")
    assert result["status"] == "completed"
    assert result["task_id"]
    assert result["plan"]["steps"]
    assert result["result"]
    assert any(t["phase"] == "plan" for t in result["trace"])
    assert any(t["phase"] == "aggregate" for t in result["trace"])
    row = get_db().fetchone("SELECT * FROM tasks WHERE id=?", (result["task_id"],))
    assert row["status"] == "completed"
