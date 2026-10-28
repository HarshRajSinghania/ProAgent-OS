from __future__ import annotations

from fastapi import APIRouter, HTTPException

from proagent_os.auth import TenantDep
from proagent_os.models.schemas import MonitorCreate
from proagent_os.services import get_services

router = APIRouter()


@router.get("")
def list_monitors(tenant: TenantDep) -> list:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    return get_services().monitors.list(tenant["id"])


@router.post("")
def create_monitor(body: MonitorCreate, tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    if body.kind not in {"kb_change", "metric_stub", "data_source"}:
        raise HTTPException(400, "kind must be kb_change|metric_stub|data_source")
    return get_services().monitors.create(
        tenant["id"], body.name, body.kind, body.config, body.interval_seconds
    )


@router.post("/{monitor_id}/run")
async def run_monitor(monitor_id: str, tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    try:
        return await get_services().monitors.run_once(tenant["id"], monitor_id)
    except KeyError:
        raise HTTPException(404, "monitor not found") from None


@router.post("/{monitor_id}/enable")
def enable_monitor(monitor_id: str, tenant: TenantDep, enabled: bool = True) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key")
    row = get_services().monitors.set_enabled(tenant["id"], monitor_id, enabled)
    if not row:
        raise HTTPException(404, "monitor not found")
    return row
