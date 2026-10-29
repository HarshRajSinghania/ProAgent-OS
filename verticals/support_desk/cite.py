"""Keyword citations for the support desk pack.

Offline helper shared by the skill runners. It quotes bundled policy fixtures
or passages the caller already retrieved (for example `kb_search` hits).
It is not a classifier you would ship to customers.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TOKEN = re.compile(r"[a-z0-9]+")
_HUMAN = re.compile(r"\b(exception|legal|lawsuit|attorney|takeover)\b")

STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "for",
        "in",
        "on",
        "is",
        "are",
        "be",
        "with",
        "that",
        "this",
        "it",
        "as",
        "at",
        "by",
        "from",
        "we",
        "our",
        "you",
        "your",
        "was",
        "were",
        "want",
        "what",
        "should",
        "support",
        "customer",
        "northwind",
        "subject",
        "after",
        "when",
        "before",
        "once",
        "not",
        "do",
        "can",
        "my",
        "me",
        "please",
        "hello",
        "thanks",
        "thank",
    }
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def query_terms(text: str) -> list[str]:
    terms: list[str] = []
    for tok in tokenize(text):
        if tok in STOP or (len(tok) <= 2 and not tok.isdigit()):
            continue
        if tok not in terms:
            terms.append(tok)
    return terms


def _variants(term: str) -> set[str]:
    found = {term}
    if len(term) > 3 and term.endswith("s"):
        found.add(term[:-1])
    if len(term) > 4 and term.endswith("ed"):
        found.add(term[:-2])
    if len(term) > 3 and term.endswith("d"):
        found.add(term[:-1])
    if len(term) > 3 and not term.endswith("s"):
        found.add(term + "s")
    return found


def _covers(term: str, tokens: set[str]) -> bool:
    return any(variant in tokens for variant in _variants(term))


def normalize_passage(raw: dict[str, Any]) -> dict[str, str] | None:
    content = str(raw.get("content") or raw.get("text") or "").strip()
    if not content:
        return None
    title = str(raw.get("title") or "").strip()
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    source = str(raw.get("source") or "")
    if source:
        source = Path(source).name
    return {"title": title or "policy", "source": source, "content": content}


def normalize_passages(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    passages: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            parsed = normalize_passage(item)
            if parsed:
                passages.append(parsed)
    return passages


def load_fixtures(directory: Path | None = None) -> list[dict[str, str]]:
    root = directory or FIXTURES_DIR
    if not root.is_dir():
        return []
    passages: list[dict[str, str]] = []
    for path in sorted(root.glob("*.md")):
        parsed = normalize_passage(
            {
                "title": path.stem.replace("_", " "),
                "source": path.name,
                "content": path.read_text(encoding="utf-8"),
            }
        )
        if parsed:
            passages.append(parsed)
    return passages


def _excerpt(content: str, terms: list[str], limit: int = 240) -> str:
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.lstrip("-* ").strip()
        if line:
            lines.append(line)
    if not lines:
        compact = re.sub(r"\s+", " ", content).strip()
        lines = [compact] if compact else []
    if not lines:
        return ""

    def hits(line: str) -> int:
        low = line.lower()
        return sum(1 for term in terms if term and term in low)

    # More term hits first. On a tie, keep the earlier line so the lead sentence wins.
    best = max(enumerate(lines), key=lambda pair: (hits(pair[1]), -pair[0]))[1]
    text = re.sub(r"\s+", " ", best).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def rank(query: str, passages: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    terms = query_terms(query)
    try:
        limit = int(top_k)
    except (TypeError, ValueError):
        limit = 3
    limit = min(max(limit, 1), 8)
    if not terms:
        return []
    ranked: list[dict[str, Any]] = []
    for raw in passages:
        if not isinstance(raw, dict):
            continue
        passage = normalize_passage(raw)
        if not passage:
            continue
        tokens = set(tokenize(passage["content"])) | set(tokenize(passage["title"]))
        hits = sum(1 for term in terms if _covers(term, tokens))
        if hits <= 0:
            continue
        ranked.append(
            {
                "title": passage["title"],
                "source": passage["source"],
                "score": round(hits / len(terms), 4),
                "excerpt": _excerpt(passage["content"], terms),
            }
        )
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["title"])))
    return ranked[:limit]


def _has(text: str, phrase: str) -> bool:
    if " " in phrase or "'" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def classify_ticket(ticket: str) -> dict[str, str]:
    """Keyword priority and category. Urgent means a person should review."""
    text = (ticket or "").lower()
    outage = any(_has(text, phrase) for phrase in ("outage", "down", "unavailable", "degraded")) or "error 500" in text
    billing = any(
        _has(text, phrase)
        for phrase in ("refund", "charge", "charged", "invoice", "billing", "payment", "subscription")
    )
    access = any(_has(text, phrase) for phrase in ("password", "login", "locked", "lockout", "mfa", "2fa")) or any(
        phrase in text for phrase in ("sign in", "log in", "cannot log", "can't log")
    )
    if outage:
        category = "outage"
    elif billing:
        category = "billing"
    elif access:
        category = "access"
    else:
        category = "general"

    urgent = category == "outage" or any(_has(text, phrase) for phrase in ("locked", "lockout", "breach", "takeover"))
    urgent = urgent or any(phrase in text for phrase in ("cannot log", "can't log"))
    if urgent:
        priority = "urgent"
    elif category == "billing":
        priority = "high"
    else:
        priority = "normal"
    return {"priority": priority, "category": category}


def needs_human(ticket: str, priority: str, citations: list[dict[str, Any]]) -> bool:
    if not citations or priority == "urgent":
        return True
    return _HUMAN.search((ticket or "").lower()) is not None
