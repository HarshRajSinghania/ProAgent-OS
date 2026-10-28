from __future__ import annotations

from typing import Any, Dict, List, Optional

from proagent_os.db import dumps, get_db, loads, utcnow


ALLOWED_STATUS = {"pending", "approved", "rejected", "executed"}


class RecommendationService:
    def __init__(self) -> None:
        self.db = get_db()

    def list(
        self,
        tenant_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if status:
            rows = self.db.fetchall(
                "SELECT * FROM recommendations WHERE tenant_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, status, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM recommendations WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            )
        for r in rows:
            r["action_payload"] = loads(r.pop("action_payload_json", "{}"), {})
        return rows

    def get(self, tenant_id: str, rec_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetchone(
            "SELECT * FROM recommendations WHERE id=? AND tenant_id=?",
            (rec_id, tenant_id),
        )
        if not row:
            return None
        row["action_payload"] = loads(row.pop("action_payload_json", "{}"), {})
        return row

    def decide(self, tenant_id: str, rec_id: str, status: str) -> Dict[str, Any]:
        if status not in {"approved", "rejected", "executed"}:
            raise ValueError("status must be approved|rejected|executed")
        row = self.get(tenant_id, rec_id)
        if not row:
            raise KeyError("recommendation not found")
        if row["status"] not in {"pending", "approved"} and status == "executed":
            # allow execute only from approved/pending
            pass
        self.db.update(
            "recommendations",
            {"status": status, "decided_at": utcnow()},
            "id=? AND tenant_id=?",
            (rec_id, tenant_id),
        )
        return self.get(tenant_id, rec_id) or {}

    def create(
        self,
        tenant_id: str,
        title: str,
        rationale: str = "",
        action: Optional[Dict[str, Any]] = None,
        monitor_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from proagent_os.db import new_id

        rec_id = new_id("rec")
        self.db.insert(
            "recommendations",
            {
                "id": rec_id,
                "tenant_id": tenant_id,
                "monitor_id": monitor_id,
                "task_id": task_id,
                "title": title,
                "rationale": rationale,
                "action_payload_json": dumps(action or {}),
                "status": "pending",
                "created_at": utcnow(),
                "decided_at": None,
            },
        )
        return self.get(tenant_id, rec_id) or {"id": rec_id}

    def acceptance_rate(self, tenant_id: str) -> Dict[str, Any]:
        rows = self.db.fetchall(
            "SELECT status, COUNT(*) AS n FROM recommendations WHERE tenant_id=? GROUP BY status",
            (tenant_id,),
        )
        counts = {r["status"]: r["n"] for r in rows}
        decided = counts.get("approved", 0) + counts.get("rejected", 0) + counts.get("executed", 0)
        approved_like = counts.get("approved", 0) + counts.get("executed", 0)
        rate = (approved_like / decided) if decided else None
        return {"counts": counts, "acceptance_rate": rate, "decided": decided}
