import re

_RULES = [
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<aws-key>"),
    (re.compile(r"\b(?:sk|xox[baprs]|ghp|gho)[-_][A-Za-z0-9_-]{16,}\b"), "<token>"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"), r"\1=<redacted>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
]


def redact(text: str) -> str:
    for rx, rep in _RULES:
        text = rx.sub(rep, text)
    return text
