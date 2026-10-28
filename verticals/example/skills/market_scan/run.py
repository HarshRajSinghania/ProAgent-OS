from __future__ import annotations

from typing import Any, Dict, List


def run(tenant_id: str = "", signals: List[str] | None = None, **_: Any) -> Dict[str, Any]:
    signals = signals or ["demand", "price", "competitor"]
    return {
        "tenant_id": tenant_id,
        "watched_signals": signals,
        "note": "Stub vertical skill — wire to real data sources in your pack.",
    }
