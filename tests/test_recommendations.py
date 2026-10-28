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
            "name": "Rec Co",
            "api_key": "pk_rec",
            "goals": "",
            "constraints": "",
            "tone": "professional",
            "created_at": utcnow(),
        },
    )
    return tid


@pytest.mark.asyncio
async def test_recommendation_approve_flow():
    tid = _tenant()
    svc = get_services()
    mon = svc.monitors.create(
        tid,
        name="Conv watch",
        kind="metric_stub",
        config={"metric": "conversion_rate", "current": 0.018, "target": 0.025},
        interval_seconds=30,
    )
    run = await svc.monitors.run_once(tid, mon["id"])
    assert "recommendation" in run
    rec_id = run["recommendation"]["id"]
    pending = svc.recommendations.list(tid, status="pending")
    assert any(r["id"] == rec_id for r in pending)

    approved = svc.recommendations.decide(tid, rec_id, "approved")
    assert approved["status"] == "approved"

    outcome = svc.metrics.record_outcome(tid, rec_id, "lift", 0.3)
    learning = svc.learning.apply_outcome_feedback(
        tid, rec_id, "lift", 0.3, skill_id="market_scan", success_threshold=0.0
    )
    assert outcome["value"] == 0.3
    assert learning["positive"] is True
    assert learning["skill_weight"]["score"] > 1.0

    rate = svc.recommendations.acceptance_rate(tid)
    assert rate["counts"].get("approved", 0) >= 1
