import re

_PATTERNS = [
    r"ignor\w*\s+(todas?\s+)?(tus|las|your|all|previous|prior)\s+(instruccion\w*|instructions?|rules?|reglas)",
    r"disregard\s+.*(instructions?|rules?)",
    r"(system|developer)\s*(prompt|message)\s*:",
    r"^\s*(system|assistant)\s*:",
    r"(show|reveal|print|muestra\w*|mostr\w*)\s+.*(system prompt|secret\w*|token\w*|password\w*|api[_ -]?key)",
    r"you are now\b|ahora eres\b|act(ua|úa) como\b",
    r"(?<!never )(?<!nunca )(?<!not )(?<!no )disable\s+(tls|ssl|verification)",
    r"(?<!nunca )(?<!no )deshabilit\w+\s+(tls|ssl|la verificaci)",
    r"post\w*\s+.*(token|secret|password)",
]
_RX = [re.compile(p, re.I | re.M) for p in _PATTERNS]


def injection_score(text: str) -> float:
    hits = sum(1 for rx in _RX if rx.search(text))
    return min(1.0, hits / 2)


def check_input(text: str, max_chars: int) -> tuple[bool, str]:
    if len(text) > max_chars:
        return False, "input too long"
    if injection_score(text) >= 0.5:
        return False, "possible prompt injection"
    return True, ""


def wrap_untrusted(label: str, content: str) -> str:
    safe = content.replace("</untrusted", "<\\/untrusted")
    return f'<untrusted source="{label}">\n{safe}\n</untrusted>'
