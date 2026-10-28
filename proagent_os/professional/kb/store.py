from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from proagent_os.db import get_db, new_id, utcnow
from proagent_os.professional.kb.chunking import chunk_text
from proagent_os.professional.kb.ingest import fetch_url_text, read_local_file
from proagent_os.professional.kb.retrieve import rank_chunks


class KnowledgeBase:
    def __init__(self) -> None:
        self.db = get_db()

    def ingest_text(self, tenant_id: str, source: str, title: str, content: str) -> Dict[str, Any]:
        doc_id = new_id("doc")
        self.db.insert(
            "kb_documents",
            {
                "id": doc_id,
                "tenant_id": tenant_id,
                "source": source,
                "title": title or source,
                "content": content,
                "created_at": utcnow(),
            },
        )
        chunks = chunk_text(content)
        for i, ch in enumerate(chunks):
            self.db.insert(
                "kb_chunks",
                {
                    "id": new_id("chk"),
                    "document_id": doc_id,
                    "tenant_id": tenant_id,
                    "chunk_index": i,
                    "content": ch,
                    "tokens_estimate": max(1, len(ch.split())),
                },
            )
        return {"document_id": doc_id, "title": title, "chunks": len(chunks), "source": source}

    async def ingest_url(self, tenant_id: str, url: str) -> Dict[str, Any]:
        title, text = await fetch_url_text(url)
        return self.ingest_text(tenant_id, source=url, title=title, content=text)

    def ingest_file(self, tenant_id: str, path: Path) -> Dict[str, Any]:
        title, text = read_local_file(path)
        return self.ingest_text(tenant_id, source=str(path), title=title, content=text)

    def list_documents(self, tenant_id: str) -> List[Dict[str, Any]]:
        return self.db.fetchall(
            "SELECT id, source, title, created_at, length(content) AS chars FROM kb_documents WHERE tenant_id=? ORDER BY created_at DESC",
            (tenant_id,),
        )

    def search(self, tenant_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        chunks = self.db.fetchall(
            "SELECT c.id, c.content, c.document_id, c.chunk_index, d.title, d.source "
            "FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id "
            "WHERE c.tenant_id=?",
            (tenant_id,),
        )
        ranked = rank_chunks(query, chunks, top_k=top_k)
        return [
            {
                "chunk_id": c["id"],
                "document_id": c["document_id"],
                "title": c["title"],
                "source": c["source"],
                "chunk_index": c["chunk_index"],
                "score": round(score, 4),
                "content": c["content"][:1000],
            }
            for c, score in ranked
        ]
