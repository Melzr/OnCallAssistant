from app import config


def render_docs(docs: list[dict], keep: tuple[str, ...] = ()) -> str:
    """Prompt text for the top-scoring docs plus any in `keep`, each truncated."""
    ranked = sorted(docs, key=lambda d: d.get("score", 0), reverse=True)
    chosen = ranked[:config.MAX_PROMPT_DOCS]
    chosen += [d for d in ranked[config.MAX_PROMPT_DOCS:] if d["id"] in keep]
    return "\n\n".join(f"[{d['id']}] {d['header']}\n{_clip(d['text'])}" for d in chosen)


def _clip(text: str) -> str:
    return text if len(text) <= config.MAX_DOC_CHARS else text[:config.MAX_DOC_CHARS].rstrip() + " [truncated]"
