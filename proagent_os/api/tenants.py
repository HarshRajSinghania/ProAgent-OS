from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException

from proagent_os.auth import AdminDep, TenantDep
from proagent_os.db import get_db, new_id, utcnow
from proagent_os.models.schemas import TenantCreate, TenantOut, TenantUpdate
from proagent_os.professional.brand.store import BrandStore

router = APIRouter()


@router.post("", response_model=TenantOut)
def create_tenant(body: TenantCreate, _admin: AdminDep) -> dict:
    tid = new_id("ten")
    api_key = f"pk_{secrets.token_urlsafe(24)}"
    get_db().insert(
        "tenants",
        {
            "id": tid,
            "name": body.name,
            "api_key": api_key,
            "goals": body.goals,
            "constraints": body.constraints,
            "tone": body.tone,
            "created_at": utcnow(),
        },
    )
    row = get_db().fetchone("SELECT * FROM tenants WHERE id=?", (tid,))
    return row  # type: ignore[return-value]


@router.get("/me")
def get_me(tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        return tenant
    return {k: tenant[k] for k in ("id", "name", "goals", "constraints", "tone", "created_at", "api_key")}


@router.patch("/me")
def update_me(body: TenantUpdate, tenant: TenantDep) -> dict:
    if tenant.get("is_admin"):
        raise HTTPException(400, "Admin has no brand profile; use a tenant key")
    store = BrandStore()
    updated = store.update(tenant["id"], goals=body.goals, constraints=body.constraints, tone=body.tone)
    return updated.__dict__ if updated else {}


@router.get("")
def list_tenants(_admin: AdminDep) -> list:
    return get_db().fetchall("SELECT id, name, goals, constraints, tone, created_at FROM tenants ORDER BY created_at DESC")
