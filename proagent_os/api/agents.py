from __future__ import annotations

from fastapi import APIRouter

from proagent_os.auth import TenantDep
from proagent_os.services import get_services

router = APIRouter()


@router.get("")
def list_agents(_tenant: TenantDep) -> list:
    svc = get_services()
    return [
        {
            "id": a.id,
            "role": a.role,
            "tools": a.tools,
            "description": a.description,
            "system_prompt": a.system_prompt[:500],
        }
        for a in svc.agents.list()
    ]


@router.get("/tools")
def list_tools(_tenant: TenantDep) -> list:
    return get_services().tools.list()
