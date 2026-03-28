"""解析布局配置加载器。

负责从 config/parse_layouts/*.yaml 加载轻量配置，供 parser 在“按类型+token位置”模式下使用。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _repoRoot() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def loadParseLayout(format_name: str) -> dict[str, Any]:
    """按格式名加载解析布局配置；不存在时返回空字典。"""
    key = (format_name or "").strip().lower()
    if not key:
        return {}
    path = _repoRoot() / "config" / "parse_layouts" / f"{key}.yaml"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        return {}
    return data
