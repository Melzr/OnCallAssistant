import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FRONT = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
_HEAD = re.compile(r"^(#{1,3})\s+(.*)$")


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict
    embed_text: str = ""
    extra: dict = field(default_factory=dict)


def parse_document(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    m = _FRONT.match(raw)
    if not m:
        raise ValueError(f"missing frontmatter: {path}")
    meta = yaml.safe_load(m.group(1))
    body = m.group(2)
    doc_id = meta["document_id"]

    sections: list[tuple[str, list[str]]] = []
    stack: list[str] = []
    for line in body.splitlines():
        h = _HEAD.match(line)
        if h:
            level = len(h.group(1))
            stack = stack[: level - 1] + [h.group(2).strip()]
            sections.append((" > ".join(stack), []))
        elif sections:
            sections[-1][1].append(line)

    chunks = []
    for idx, (section, lines) in enumerate(sections):
        text = "\n".join(lines).strip()
        if not text:
            continue
        md = {
            "document": meta["document"],
            "document_id": doc_id,
            "doc_type": meta["doc_type"],
            "section": section,
            "page": None,
            "version": str(meta["version"]),
            "status": meta.get("status", "current"),
            "replaces": meta.get("replaces"),
            "related_to": meta.get("related_to", []),
            "service": meta["service"],
            "category": meta.get("category"),
            "source": meta["source"],
            "owner": meta.get("owner"),
            "updated_at": str(meta["updated_at"]),
            "acl": meta.get("acl", []),
            "hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        }
        slug = re.sub(r"[^a-z0-9]+", "-", section.split(" > ")[-1].lower()).strip("-")
        chunks.append(Chunk(
            id=f"{doc_id}#{slug}",
            text=text,
            metadata=md,
            embed_text=f"{meta['document']} > {section} ({meta['service']})\n{text}",
        ))
    return chunks
