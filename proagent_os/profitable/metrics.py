from __future__ import annotations

from typing import Any, Dict, List, Optional

from proagent_os.db import dumps, get_db, new_id, utcnow


class MetricsAdapter:
    """Interface: record_outcome(action_id, metric_name, value)."""

    def __init__(self) -> None:
        self.db = get_db()

    def record_outcome(
        self,
        tenant_id: str,
        action_id: str,
        metric_name: str,
        value: float,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        oid = new_id("out")
        self.db.insert(
            "outcomes",
            {
                "id": oid,
                "tenant_id": tenant_id,
                "action_id": action_id,
                "metric_name": metric_name,
                "value": float(value),
                "meta_json": dumps(meta or {}),
                "created_at": utcnow(),
            },
        )
        return {"id": oid, "action_id": action_id, "metric_name": metric_name, "value": value}

    def list_outcomes(self, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM outcomes WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        )

    def summary(self, tenant_id: str) -> Dict[str, Any]:
        rows = self.db.fetchall(
            "SELECT metric_name, COUNT(*) AS n, AVG(value) AS avg_value, SUM(value) AS sum_value "
            "FROM outcomes WHERE tenant_id=? GROUP BY metric_name",
            (tenant_id,),
        )
        return {"by_metric": rows, "total": sum(r["n"] for r in rows)}
