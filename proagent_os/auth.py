from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from proagent_os.config import get_settings
from proagent_os.db import get_db


async def require_tenant(
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    if token == settings.admin_key:
        return {"id": "admin", "name": "Admin", "api_key": token, "is_admin": True}
    row = get_db().fetchone("SELECT * FROM tenants WHERE api_key = ?", (token,))
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    row["is_admin"] = False
    return row


async def require_admin(tenant: Annotated[dict, Depends(require_tenant)]) -> dict:
    if not tenant.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
    return tenant


TenantDep = Annotated[dict, Depends(require_tenant)]
AdminDep = Annotated[dict, Depends(require_admin)]
