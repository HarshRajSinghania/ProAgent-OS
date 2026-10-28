from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import httpx
from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def fetch_url_text(url: str) -> Tuple[str, str]:
    """Return (title, text). Supports fixture:// for offline demos."""
    if url.startswith("fixture://"):
        name = url.replace("fixture://", "")
        path = Path("fixtures") / name
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".html", ".htm"}:
            title = path.stem
            soup = BeautifulSoup(raw, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            return title, html_to_text(raw)
        return path.stem, raw

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "ProAgentOS/0.1"})
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype or url.endswith((".html", ".htm")):
            title = url
            soup = BeautifulSoup(resp.text, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            return title, html_to_text(resp.text)
        return url, resp.text


def read_local_file(path: Path) -> Tuple[str, str]:
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".pdf":
        # Best-effort PDF text without hard dependency on pypdf
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(__import__("io").BytesIO(raw))
            pages = [p.extract_text() or "" for p in reader.pages]
            return path.stem, "\n\n".join(pages)
        except Exception:
            # Fallback: extract printable strings
            text = "".join(chr(b) if 32 <= b < 127 else "\n" for b in raw)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return path.stem, text.strip()[:50000]
    text = raw.decode("utf-8", errors="ignore")
    if suffix in {".html", ".htm"}:
        return path.stem, html_to_text(text)
    return path.stem, text
