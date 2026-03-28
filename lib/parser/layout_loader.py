"""lib.parser 布局配置加载。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _layout_dir() -> Path:
    return Path(__file__).resolve().parent / "layouts"


@lru_cache(maxsize=8)
def load_layout(format_name: str) -> dict[str, Any]:
    """加载指定格式布局配置。"""
    key = (format_name or "").strip().lower()
    if not key:
        raise ValueError("format_name is required")
    path = _layout_dir() / f"{key}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"layout not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"layout should be dict: {path}")
    return data
