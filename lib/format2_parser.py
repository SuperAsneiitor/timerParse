from __future__ import annotations

# 兼容旧导入路径：
#   from lib.format2_parser import Format2Parser, _desc_to_point, _tail_n_numeric_and_desc, _is_numeric_token
from .parsers.format2_parser import (
    Format2Parser,
    _desc_to_point,
    _tail_n_numeric_and_desc,
    _is_numeric_token,
)

__all__ = ["Format2Parser", "_desc_to_point", "_tail_n_numeric_and_desc", "_is_numeric_token"]

