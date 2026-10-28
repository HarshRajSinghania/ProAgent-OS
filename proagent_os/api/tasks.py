from __future__ import annotations

from fastapi import APIRouter, HTTPException

from proagent_os.auth import TenantDep
from proagent_os.db import get_db, loads
from proagent_os.models.schemas import TaskCreate
from proagent_os.services import get_services

router = APIRouter()


@router.post("")
async def create_task(body: TaskCreate, tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Use a tenant API key to run tasks")
    svc = get_services()
    result = await svc.orchestrator.run_task(
        tenant["id"],
        body.input,
        conversation_id=body.conversation_id,
    )
    return result


@router.get("")
def list_tasks(tenant: TenantDep, limit: int = 50) -> list:
    tid = tenant["id"]
    if tenant.get("is_admin"):
        return get_db().fetchall("SELECT id, tenant_id, status, input, created_at, updated_at FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
    return get_db().fetchall(
        "SELECT id, tenant_id, status, input, created_at, updated_at FROM tasks WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
        (tid, limit),
    )


@router.get("/{task_id}")
def get_task(task_id: str, tenant: TenantDep) -> dict:
    row = get_db().fetchone("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not row:
        raise HTTPException(404, "task not found")
    if not tenant.get("is_admin") and row["tenant_id"] != tenant["id"]:
        raise HTTPException(404, "task not found")
    row["plan"] = loads(row.pop("plan_json", "[]"), [])
    row["trace"] = loads(row.pop("trace_json", "[]"), [])
    return row
