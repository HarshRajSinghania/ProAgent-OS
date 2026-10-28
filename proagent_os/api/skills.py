from __future__ import annotations

from fastapi import APIRouter, HTTPException

from proagent_os.auth import TenantDep
from proagent_os.models.schemas import SkillInvoke
from proagent_os.services import get_services

router = APIRouter()


@router.get("")
def list_skills(_tenant: TenantDep) -> list:
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "path": str(s.path),
            "has_runner": s.runner is not None,
            "metadata": s.metadata,
        }
        for s in get_services().skills.list()
    ]


@router.get("/{skill_id}")
def get_skill(skill_id: str, _tenant: TenantDep) -> dict:
    skill = get_services().skills.get(skill_id)
    if not skill:
        raise HTTPException(404, "skill not found")
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "body": skill.body,
        "has_runner": skill.runner is not None,
        "metadata": skill.metadata,
    }


@router.post("/{skill_id}/invoke")
async def invoke_skill(skill_id: str, body: SkillInvoke, tenant: TenantDep) -> dict:
    try:
        result = await get_services().skills.invoke(skill_id, tenant_id=tenant["id"], **body.arguments)
    except KeyError:
        raise HTTPException(404, "skill not found") from None
    return {"skill_id": skill_id, "result": result}
