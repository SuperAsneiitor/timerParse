"""轻量布局解析运行时。

按照“先分类 point 类型，再按 token 位置提取字段”的方式提供通用能力。
"""
from __future__ import annotations

import re
from typing import Any

from .layout_config import loadParseLayout


class LayoutRuntime:
    """按格式加载布局配置，提供分类与 token 位置提取能力。"""

    def __init__(self, format_name: str) -> None:
        self.layout = loadParseLayout(format_name)

    @staticmethod
    def splitTokens(line: str) -> list[str]:
        return line.strip().split()

    def classifyPointType(self, line: str, type_hint: str = "") -> str:
        """按配置规则分类 point 类型；若无命中则回退 type_hint。"""
        rules = self.layout.get("type_classify") or []
        text_low = (line or "").lower()
        tokens = self.splitTokens(line)
        ordered = sorted(rules, key=lambda r: int((r or {}).get("priority", 0)), reverse=True)
        for rule in ordered:
            when = (rule or {}).get("when") or {}
            if self._matchWhen(when, text_low, tokens):
                return str((rule or {}).get("emit") or "").strip().lower()
        hint = (type_hint or "").strip().lower()
        return hint

    @staticmethod
    def _matchWhen(when: dict[str, Any], text_low: str, tokens: list[str]) -> bool:
        contains = str(when.get("contains") or "").strip().lower()
        if contains and contains not in text_low:
            return False
        regex = str(when.get("regex") or "").strip()
        if regex and not re.search(regex, text_low, re.IGNORECASE):
            return False
        token_eq = when.get("token_eq") or {}
        if token_eq:
            idx = int(token_eq.get("index", -999))
            val = str(token_eq.get("value") or "").strip().lower()
            if idx < 0 or idx >= len(tokens) or tokens[idx].strip().lower() != val:
                return False
        return True

    @staticmethod
    def extractTailNumeric(line: str, fields: list[str]) -> dict[str, str]:
        """从行尾按顺序提取数值并映射到字段。"""
        nums = re.findall(r"-?\d+(?:\.\d+)?", line or "")
        if not nums:
            return {}
        n = min(len(nums), len(fields))
        tail = nums[-n:] if n else []
        out: dict[str, str] = {}
        for i, name in enumerate(fields[:n]):
            out[name] = tail[i]
        return out

    @staticmethod
    def extractPointAfterLastNumeric(line: str) -> str:
        """提取最后一个数值 token 之后的文本作为 point/description。"""
        tokens = (line or "").split()
        last_num = -1
        for i in range(len(tokens) - 1, -1, -1):
            if re.fullmatch(r"-?\d+(?:\.\d+)?", tokens[i]):
                last_num = i
                break
        if last_num < 0:
            return " ".join(tokens[1:]).strip()
        return " ".join(tokens[last_num + 1 :]).strip()

    @staticmethod
    def extractTriggerEdge(line: str) -> str:
        m = re.search(r"\s([/\\])\s*(?:\S.*)?$", (line or "").strip())
        if not m:
            return ""
        return "r" if m.group(1) == "/" else "f"

    def extractRowKindNumeric(self, row_kind: str, line: str) -> dict[str, str] | None:
        """按配置的 row_kind_numeric 映射提取尾部数值。"""
        mapping = (self.layout.get("row_kind_numeric") or {}).get(row_kind)
        if not mapping:
            return None
        fields = [str(x) for x in mapping if str(x)]
        if not fields:
            return None
        return self.extractTailNumeric(line, fields)

    def extractByTypeLayout(self, point_type: str, line: str) -> dict[str, str]:
        """按 type_layouts 规则抽取字段（轻量模式）。"""
        cfg = (self.layout.get("type_layouts") or {}).get(point_type) or {}
        out: dict[str, str] = {}
        tail_fields = [str(x) for x in (cfg.get("tail_numeric") or []) if str(x)]
        if tail_fields:
            out.update(self.extractTailNumeric(line, tail_fields))
        if str(cfg.get("point_from") or "") == "after_last_numeric":
            out["point"] = self.extractPointAfterLastNumeric(line)
        return out
