from __future__ import annotations

from fastapi import APIRouter, HTTPException

from proagent_os.auth import TenantDep
from proagent_os.db import get_db
from proagent_os.services import get_services

router = APIRouter()


@router.get("")
def dashboard(tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    tid = tenant["id"]
    svc = get_services()
    tasks = get_db().fetchall(
        "SELECT status, COUNT(*) AS n FROM tasks WHERE tenant_id=? GROUP BY status",
        (tid,),
    )
    return {
        "tenant_id": tid,
        "tasks": {r["status"]: r["n"] for r in tasks},
        "recommendations": svc.recommendations.acceptance_rate(tid),
        "outcomes": svc.metrics.summary(tid),
        "skill_weights": svc.learning.list_weights(tid),
        "documents": len(svc.kb.list_documents(tid)),
        "monitors": len(svc.monitors.list(tid)),
        "skills": len(svc.skills.list()),
    }
