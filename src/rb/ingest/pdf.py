"""Estrazione da PDF scientifici: testo, identificativi (DOI, arXiv), grandezze riportate."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from rb.ingest.quantities import extract_quantities

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+[A-Za-z0-9]")
ARXIV_RE = re.compile(r"arXiv:\s?(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)


def extract_identifiers(text: str) -> dict:
    dois = sorted({d.rstrip(".,;)") for d in DOI_RE.findall(text)})
    arxiv = sorted({m.group(1) for m in ARXIV_RE.finditer(text)})
    return {"dois": dois, "arxiv_ids": arxiv}


def parse_pdf(path: str | Path, max_pages: int = 300) -> dict:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages[:max_pages]]
    text = "\n".join(pages)
    title = None
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title).strip() or None
    if not title:
        title = next((ln.strip() for ln in text.splitlines() if 8 <= len(ln.strip()) <= 200), None)
    return {
        "title": title,
        "n_pages": len(reader.pages),
        "text": text,
        **extract_identifiers(text),
        "quantities": [q.to_dict() for q in extract_quantities(text)],
    }
