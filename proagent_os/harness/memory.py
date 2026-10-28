from __future__ import annotations

from typing import Any, Dict, List, Optional

from proagent_os.db import dumps, get_db, new_id, utcnow


class ConversationMemory:
    def __init__(self) -> None:
        self.db = get_db()

    def create_conversation(self, tenant_id: str, title: str = "") -> str:
        cid = new_id("conv")
        self.db.insert(
            "conversations",
            {"id": cid, "tenant_id": tenant_id, "title": title, "created_at": utcnow()},
        )
        return cid

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        mid = new_id("msg")
        self.db.insert(
            "messages",
            {
                "id": mid,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "meta_json": dumps(meta or {}),
                "created_at": utcnow(),
            },
        )
        return mid

    def history(self, conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC LIMIT ?",
            (conversation_id, limit),
        )

    def append_tenant_memory(self, tenant_id: str, kind: str, content: str) -> str:
        mid = new_id("mem")
        self.db.insert(
            "tenant_memory",
            {
                "id": mid,
                "tenant_id": tenant_id,
                "kind": kind,
                "content": content,
                "created_at": utcnow(),
            },
        )
        return mid

    def list_tenant_memory(self, tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM tenant_memory WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        )
