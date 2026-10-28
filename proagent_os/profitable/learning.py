from __future__ import annotations

from typing import Any, Dict, Optional

from proagent_os.db import get_db, utcnow
from proagent_os.harness.memory import ConversationMemory


class LearningLoop:
    """
    Stub learning loop: after outcomes, append feedback into tenant memory
    and nudge skill weights (simple score, not real RL).
    """

    def __init__(self) -> None:
        self.db = get_db()
        self.memory = ConversationMemory()

    def apply_outcome_feedback(
        self,
        tenant_id: str,
        action_id: str,
        metric_name: str,
        value: float,
        *,
        skill_id: Optional[str] = None,
        success_threshold: float = 0.0,
    ) -> Dict[str, Any]:
        positive = value >= success_threshold
        note = (
            f"Outcome feedback: action={action_id} metric={metric_name} value={value} "
            f"({'positive' if positive else 'negative'})"
        )
        mem_id = self.memory.append_tenant_memory(tenant_id, kind="outcome_feedback", content=note)

        weight_update = None
        if skill_id:
            weight_update = self._nudge_skill(tenant_id, skill_id, +0.05 if positive else -0.05)

        return {"memory_id": mem_id, "positive": positive, "skill_weight": weight_update}

    def _nudge_skill(self, tenant_id: str, skill_id: str, delta: float) -> Dict[str, Any]:
        row = self.db.fetchone(
            "SELECT * FROM skill_weights WHERE tenant_id=? AND skill_id=?",
            (tenant_id, skill_id),
        )
        now = utcnow()
        if not row:
            score = max(0.1, 1.0 + delta)
            self.db.insert(
                "skill_weights",
                {
                    "tenant_id": tenant_id,
                    "skill_id": skill_id,
                    "score": score,
                    "updates": 1,
                    "updated_at": now,
                },
            )
            return {"skill_id": skill_id, "score": score, "updates": 1}
        score = max(0.1, float(row["score"]) + delta)
        updates = int(row["updates"]) + 1
        self.db.update(
            "skill_weights",
            {"score": score, "updates": updates, "updated_at": now},
            "tenant_id=? AND skill_id=?",
            (tenant_id, skill_id),
        )
        return {"skill_id": skill_id, "score": score, "updates": updates}

    def list_weights(self, tenant_id: str) -> list:
        return self.db.fetchall(
            "SELECT * FROM skill_weights WHERE tenant_id=? ORDER BY score DESC",
            (tenant_id,),
        )
