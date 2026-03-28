"""lib.parser 行分类器。"""
from __future__ import annotations

import re
from typing import Any

from .tokenizer import split_tokens


def classify_line(line: str, rules: list[dict[str, Any]], default_type: str = "other") -> str:
    """按优先级规则分类行类型。"""
    text = (line or "").strip()
    low = text.lower()
    tokens = split_tokens(text)
    ordered = sorted(rules or [], key=lambda x: int((x or {}).get("priority", 0)), reverse=True)
    for rule in ordered:
        if _match_when(low, tokens, (rule or {}).get("when") or {}):
            return str((rule or {}).get("emit") or default_type).strip().lower()
    return default_type


def _match_when(text_low: str, tokens: list[str], when: dict[str, Any]) -> bool:
    contains = str(when.get("contains") or "").strip().lower()
    if contains and contains not in text_low:
        return False
    regex = str(when.get("regex") or "").strip()
    if regex and not re.search(regex, text_low, re.IGNORECASE):
        return False
    token_eq = when.get("token_eq") or {}
    if token_eq:
        idx = int(token_eq.get("index", -1))
        val = str(token_eq.get("value") or "").strip().lower()
        if idx < 0 or idx >= len(tokens):
            return False
        if tokens[idx].strip().lower() != val:
            return False
    return True
