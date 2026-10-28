from __future__ import annotations

from typing import Any, Dict, List, Optional

from proagent_os.db import dumps, get_db, loads, new_id, utcnow
from proagent_os.professional.kb.store import KnowledgeBase
from proagent_os.proactive.recommendations import RecommendationService


class MonitorService:
    def __init__(self) -> None:
        self.db = get_db()
        self.recs = RecommendationService()
        self.kb = KnowledgeBase()

    def create(
        self,
        tenant_id: str,
        name: str,
        kind: str,
        config: Dict[str, Any],
        interval_seconds: int = 60,
    ) -> Dict[str, Any]:
        mid = new_id("mon")
        self.db.insert(
            "monitors",
            {
                "id": mid,
                "tenant_id": tenant_id,
                "name": name,
                "kind": kind,
                "config_json": dumps(config),
                "interval_seconds": interval_seconds,
                "enabled": 1,
                "last_run_at": None,
                "created_at": utcnow(),
            },
        )
        return self.get(tenant_id, mid) or {"id": mid}

    def list(self, tenant_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM monitors WHERE tenant_id=? ORDER BY created_at DESC",
            (tenant_id,),
        )
        for r in rows:
            r["config"] = loads(r.pop("config_json", "{}"), {})
            r["enabled"] = bool(r["enabled"])
        return rows

    def get(self, tenant_id: str, monitor_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetchone(
            "SELECT * FROM monitors WHERE id=? AND tenant_id=?",
            (monitor_id, tenant_id),
        )
        if not row:
            return None
        row["config"] = loads(row.pop("config_json", "{}"), {})
        row["enabled"] = bool(row["enabled"])
        return row

    def set_enabled(self, tenant_id: str, monitor_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        self.db.update(
            "monitors",
            {"enabled": 1 if enabled else 0},
            "id=? AND tenant_id=?",
            (monitor_id, tenant_id),
        )
        return self.get(tenant_id, monitor_id)

    async def run_once(self, tenant_id: str, monitor_id: str) -> Dict[str, Any]:
        mon = self.get(tenant_id, monitor_id)
        if not mon:
            raise KeyError("monitor not found")
        kind = mon["kind"]
        config = mon["config"]
        result: Dict[str, Any] = {"monitor_id": monitor_id, "kind": kind}

        if kind == "kb_change":
            docs = self.kb.list_documents(tenant_id)
            threshold = int(config.get("min_docs", 1))
            result["doc_count"] = len(docs)
            if len(docs) >= threshold:
                rec = self.recs.create(
                    tenant_id,
                    title=config.get("title") or f"KB update check: {len(docs)} documents",
                    rationale=f"Monitor '{mon['name']}' detected {len(docs)} KB documents (threshold={threshold}).",
                    action={"type": "review_kb", "doc_count": len(docs)},
                    monitor_id=monitor_id,
                )
                result["recommendation"] = rec
        elif kind == "metric_stub":
            # Fake metric reading
            metric_name = config.get("metric", "conversion_rate")
            current = float(config.get("current", 0.8))
            target = float(config.get("target", 1.0))
            result["metric"] = {"name": metric_name, "current": current, "target": target}
            if current < target:
                rec = self.recs.create(
                    tenant_id,
                    title=config.get("title") or f"{metric_name} below target",
                    rationale=f"{metric_name}={current} < target={target}. Suggest corrective action.",
                    action={"type": "optimize_metric", "metric": metric_name, "current": current, "target": target},
                    monitor_id=monitor_id,
                )
                result["recommendation"] = rec
        elif kind == "data_source":
            query = config.get("query") or mon["name"]
            hits = self.kb.search(tenant_id, query, top_k=3)
            result["hits"] = hits
            if hits:
                top = hits[0]
                rec = self.recs.create(
                    tenant_id,
                    title=config.get("title") or f"Signal from KB: {top.get('title')}",
                    rationale=f"Monitor found relevant content (score={top.get('score')}): {top.get('content', '')[:240]}",
                    action={"type": "follow_up", "chunk_id": top.get("chunk_id"), "query": query},
                    monitor_id=monitor_id,
                )
                result["recommendation"] = rec
            else:
                rec = self.recs.create(
                    tenant_id,
                    title=config.get("title") or f"No KB hits for '{query}' — consider ingest",
                    rationale="Data source monitor found no matching knowledge; recommend ingesting new material.",
                    action={"type": "ingest_more", "query": query},
                    monitor_id=monitor_id,
                )
                result["recommendation"] = rec
        else:
            raise ValueError(f"Unknown monitor kind: {kind}")

        self.db.update(
            "monitors",
            {"last_run_at": utcnow()},
            "id=? AND tenant_id=?",
            (monitor_id, tenant_id),
        )
        return result

    def due_monitors(self) -> List[Dict[str, Any]]:
        rows = self.db.fetchall("SELECT * FROM monitors WHERE enabled=1")
        due = []
        now = utcnow()
        for r in rows:
            r["config"] = loads(r.pop("config_json", "{}"), {})
            # Simple: always treat as due if never run, else rely on worker interval scheduling
            due.append(r)
        return due
