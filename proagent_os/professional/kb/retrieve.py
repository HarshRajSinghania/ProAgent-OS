from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence, Tuple


_TOKEN = re.compile(r"[a-z0-9_]+", re.I)


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def bm25_scores(
    query: str,
    documents: Sequence[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> List[float]:
    """Simple offline BM25-style ranking (no external deps)."""
    q_tokens = tokenize(query)
    if not q_tokens or not documents:
        return [0.0] * len(documents)

    docs_tokens = [tokenize(d) for d in documents]
    N = len(docs_tokens)
    avgdl = sum(len(d) for d in docs_tokens) / max(N, 1)

    df: Dict[str, int] = Counter()
    for toks in docs_tokens:
        for term in set(toks):
            df[term] += 1

    scores: List[float] = []
    for toks in docs_tokens:
        tf = Counter(toks)
        dl = len(toks) or 1
        score = 0.0
        for term in q_tokens:
            if term not in tf:
                continue
            n_qi = df.get(term, 0)
            idf = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * dl / avgdl)
            score += idf * (freq * (k1 + 1)) / denom
        scores.append(score)
    return scores


def embedding_stub(text: str) -> List[float]:
    """Deterministic hash-bag embedding stub (64 dims) for future vector backends."""
    dims = 64
    vec = [0.0] * dims
    for tok in tokenize(text):
        h = hash(tok)
        vec[h % dims] += 1.0
        vec[(h // dims) % dims] += 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def rank_chunks(query: str, chunks: Sequence[Dict], top_k: int = 5) -> List[Tuple[Dict, float]]:
    docs = [c.get("content", "") for c in chunks]
    scores = bm25_scores(query, docs)
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [(c, s) for c, s in ranked[:top_k] if s > 0]
