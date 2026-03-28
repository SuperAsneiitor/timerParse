"""parser_V2 字段抽取器。"""
from __future__ import annotations

import re
from typing import Any

from .tokenizer import extract_tail_numbers, normalize_point_text, split_tokens, text_after_last_number


def extract_attrs_by_type(line: str, point_type: str, layout: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """按 point_type 配置提取 point 与属性。"""
    point = ""
    attrs: dict[str, str] = {}
    type_layouts = (layout.get("type_layouts") or {})
    cfg = (type_layouts.get(point_type) or {})

    if point_type == "net":
        return _extractNetAttrs(line, cfg)

    tail_fields = [str(x) for x in (cfg.get("tail_numeric") or []) if str(x)]
    if tail_fields:
        vals = extract_tail_numbers(line, len(tail_fields))
        if vals:
            start = max(0, len(tail_fields) - len(vals))
            for i, v in enumerate(vals):
                attrs[tail_fields[start + i]] = v

    point_from = str(cfg.get("point_from") or "").strip().lower()
    if point_from == "after_last_numeric":
        point = normalize_point_text(text_after_last_number(line))

    # 支持简单 token 索引映射（0-based）
    for col, spec in (cfg.get("token_map") or {}).items():
        if isinstance(spec, int):
            point_tokens = split_tokens(line)
            if 0 <= spec < len(point_tokens):
                attrs[str(col)] = point_tokens[spec]
        elif isinstance(spec, list) and len(spec) == 2:
            lo, hi = int(spec[0]), int(spec[1])
            point_tokens = split_tokens(line)
            lo = max(0, lo)
            hi = min(len(point_tokens) - 1, hi)
            if lo <= hi and point_tokens:
                attrs[str(col)] = " ".join(point_tokens[lo : hi + 1])

    return point, attrs


def _extractNetAttrs(line: str, cfg: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """语义化提取 net 行：支持 Cap 后单位变化（xd/xf/...）。"""
    tokens = split_tokens(line)
    attrs: dict[str, str] = {}
    if len(tokens) < 3:
        return "", attrs
    fanout_idx = int(cfg.get("fanout_idx", 1))
    cap_idx = int(cfg.get("cap_idx", 2))
    desc_start_idx = int(cfg.get("desc_start_idx", 3))
    unit_re = re.compile(str(cfg.get("unit_marker_regex") or r"^[a-zA-Z]{1,8}$"))

    if 0 <= fanout_idx < len(tokens):
        attrs["Fanout"] = tokens[fanout_idx]

    cap_token = tokens[cap_idx] if 0 <= cap_idx < len(tokens) else ""
    cap_val, cap_unit = _splitNumAndUnit(cap_token)
    if cap_val:
        attrs["Cap"] = cap_val
    elif cap_token:
        attrs["Cap"] = cap_token
    if cap_unit:
        attrs["CapUnit"] = cap_unit

    start = min(max(0, desc_start_idx), len(tokens))
    if start < len(tokens):
        marker = tokens[start]
        # 若 Cap 后紧跟“短字母单位标记”，则从描述中跳过它，避免污染 point。
        if unit_re.fullmatch(marker) and "/" not in marker and "(" not in marker and ")" not in marker:
            attrs["CapUnit"] = attrs.get("CapUnit") or marker
            start += 1
    point = normalize_point_text(" ".join(tokens[start:]))
    return point, attrs


def _splitNumAndUnit(token: str) -> tuple[str, str]:
    """拆分形如 0.003xf 的数值与单位。"""
    txt = (token or "").strip()
    if not txt:
        return "", ""
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)([a-zA-Z]+)?", txt)
    if not m:
        return "", ""
    return m.group(1) or "", m.group(2) or ""
