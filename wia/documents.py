"""Load controlled documents and split them into section-level chunks.

Each document is Markdown with YAML front matter (doc_id, revision, status, ...).
Only APPROVED documents are indexed. If several approved revisions exist for the
same doc_id, only the latest one is kept. This is the "configuration control" part.
"""
import logging
from pathlib import Path

import yaml

from .schemas import Chunk

log = logging.getLogger(__name__)


def parse_document(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path.name}: missing front matter")
    _, front, body = raw.split("---", 2)
    meta = yaml.safe_load(front) or {}
    for field in ("doc_id", "title", "revision", "status"):
        if not meta.get(field):
            raise ValueError(f"{path.name}: missing required field '{field}'")
    meta["revision"] = str(meta["revision"])
    meta["effective_date"] = str(meta.get("effective_date") or "")
    return meta, body.strip()


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split Markdown on '# ' headings -> [(section_title, text), ...]."""
    sections, title, lines = [], "Introduction", []
    for line in body.splitlines():
        if line.startswith("#"):
            if any(l.strip() for l in lines):
                sections.append((title, "\n".join(lines).strip()))
            title, lines = line.lstrip("#").strip(), []
        else:
            lines.append(line)
    if any(l.strip() for l in lines):
        sections.append((title, "\n".join(lines).strip()))
    return sections


def load_all(docs_dir: Path) -> list[dict]:
    """Return every document (all statuses) with metadata + body."""
    docs = []
    for path in sorted(docs_dir.glob("*.md")):
        try:
            meta, body = parse_document(path)
        except ValueError as e:
            log.warning("Skipping document: %s", e)
            continue
        docs.append({**meta, "body": body, "file": path.name})
    return docs


def controlled_set(docs: list[dict]) -> list[dict]:
    """Keep only approved docs, and only the latest approved revision per doc_id."""
    latest: dict[str, dict] = {}
    for d in docs:
        if d["status"] != "approved":
            log.info("Excluded %s rev %s (status=%s)", d["doc_id"], d["revision"], d["status"])
            continue
        current = latest.get(d["doc_id"])
        if current is None or d["revision"] > current["revision"]:
            latest[d["doc_id"]] = d
    return list(latest.values())


def build_chunks(docs: list[dict]) -> list[Chunk]:
    chunks = []
    for d in docs:
        for i, (section, text) in enumerate(split_sections(d["body"])):
            chunks.append(Chunk(
                chunk_id=f"{d['doc_id']}-{d['revision']}-{i}",
                doc_id=d["doc_id"], title=d["title"], revision=d["revision"],
                status=d["status"], effective_date=d["effective_date"],
                section=section, text=text,
            ))
    return chunks
