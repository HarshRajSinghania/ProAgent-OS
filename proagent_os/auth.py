from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from proagent_os.config import get_settings
from proagent_os.db import get_db
from proagent_os.keys import key_usable


def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


async def require_tenant(
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    token = extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    settings = get_settings()
    if token == settings.admin_key:
        return {
            "id": "admin",
            "name": "Admin",
            "api_key": token,
            "is_admin": True,
            "key_status": "active",
        }
    row = get_db().fetchone("SELECT * FROM tenants WHERE api_key = ?", (token,))
    # Revoked and unknown secrets share one error so a revoked key is not confirmed.
    if not row or not key_usable(row):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    row["is_admin"] = False
    return row


async def require_admin(tenant: Annotated[dict, Depends(require_tenant)]) -> dict:
    if not tenant.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
    return tenant


TenantDep = Annotated[dict, Depends(require_tenant)]
AdminDep = Annotated[dict, Depends(require_admin)]
