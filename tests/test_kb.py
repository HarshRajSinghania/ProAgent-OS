from __future__ import annotations

import pytest

from proagent_os.db import get_db, new_id, utcnow
from proagent_os.professional.kb.retrieve import bm25_scores, tokenize
from proagent_os.services import get_services


def test_tokenize_and_bm25():
    docs = [
        "conversion rate dropped below target",
        "unrelated weather forecast sunny",
        "improve activation to lift conversion",
    ]
    scores = bm25_scores("conversion activation", docs)
    assert scores[0] > scores[1]
    assert scores[2] > scores[1]
    assert "conversion" in tokenize("Conversion-Rate_v2")


@pytest.mark.asyncio
async def test_kb_ingest_and_search():
    tid = new_id("ten")
    get_db().insert(
        "tenants",
        {
            "id": tid,
            "name": "KB Co",
            "api_key": "pk_kb",
            "goals": "",
            "constraints": "",
            "tone": "professional",
            "created_at": utcnow(),
        },
    )
    kb = get_services().kb
    meta = await kb.ingest_url(tid, "fixture://sample_product.html")
    assert meta["chunks"] >= 1
    hits = kb.search(tid, "conversion rate target", top_k=3)
    assert hits
    assert hits[0]["score"] > 0
    assert "conversion" in hits[0]["content"].lower() or "target" in hits[0]["content"].lower()
