from __future__ import annotations

from fastapi import APIRouter, HTTPException

from proagent_os.auth import TenantDep
from proagent_os.models.schemas import OutcomeCreate
from proagent_os.services import get_services

router = APIRouter()


@router.post("/outcomes")
def record_outcome(body: OutcomeCreate, tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    svc = get_services()
    outcome = svc.metrics.record_outcome(
        tenant["id"], body.action_id, body.metric_name, body.value, body.meta
    )
    learning = svc.learning.apply_outcome_feedback(
        tenant["id"],
        body.action_id,
        body.metric_name,
        body.value,
        skill_id=body.skill_id,
        success_threshold=body.success_threshold,
    )
    return {"outcome": outcome, "learning": learning}


@router.get("/outcomes")
def list_outcomes(tenant: TenantDep) -> list:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    return get_services().metrics.list_outcomes(tenant["id"])
