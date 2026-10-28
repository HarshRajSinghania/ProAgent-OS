from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from proagent_os.db import get_db


@dataclass
class BrandContext:
    tenant_id: str
    name: str
    goals: str = ""
    constraints: str = ""
    tone: str = "professional"

    def prompt_block(self) -> str:
        return (
            f"Tenant/Brand: {self.name}\n"
            f"Goals: {self.goals or 'n/a'}\n"
            f"Constraints: {self.constraints or 'n/a'}\n"
            f"Tone: {self.tone}"
        )


class BrandStore:
    def get(self, tenant_id: str) -> Optional[BrandContext]:
        row = get_db().fetchone("SELECT * FROM tenants WHERE id=?", (tenant_id,))
        if not row:
            return None
        return BrandContext(
            tenant_id=row["id"],
            name=row["name"],
            goals=row.get("goals") or "",
            constraints=row.get("constraints") or "",
            tone=row.get("tone") or "professional",
        )

    def update(self, tenant_id: str, *, goals: Optional[str] = None, constraints: Optional[str] = None, tone: Optional[str] = None) -> Optional[BrandContext]:
        data = {}
        if goals is not None:
            data["goals"] = goals
        if constraints is not None:
            data["constraints"] = constraints
        if tone is not None:
            data["tone"] = tone
        if data:
            get_db().update("tenants", data, "id=?", (tenant_id,))
        return self.get(tenant_id)
