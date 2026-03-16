"""
parser_chaos 通用工具函数。

提供 pin 归一化、浮点清理、固定列宽解析等，供分割器、解析器、聚合器共用。
与 lib.parsers 完全独立。
"""
from __future__ import annotations

import re
from typing import Any


def normalizePin(pin: str) -> str:
    """
    归一化 pin 显示字符串。

    逻辑：去掉末尾的 '<-'；若包含 " (" 则截断为括号前部分（去掉 CELL_TYPE）。
    用于 launch 段按 startpoint 拆分时的名称匹配。
    """
    if not pin:
        return ""
    s = pin.strip()
    if s.endswith("<-"):
        s = s[:-2].strip()
    if " (" in s:
        s = s.split(" (", 1)[0].strip()
    return s


def cleanMetricFloat(v: float, ndigits: int = 6) -> float:
    """
    消除浮点累计噪声。

    将浮点数四舍五入到指定小数位，避免 CSV 中出现 0.39000000000000001 这类显示。
    """
    return round(float(v), ndigits)


def extractColumnPositions(header_line: str, attrs_order: list[str]) -> dict[str, int]:
    """
    从表头行解析各列名的起始字符位置，用于固定列宽解析。

    对 attrs_order 中每个列名，在 header_line 中查找 " ColName " 或 ColName 的起始下标。
    返回 { 列名: 起始位置 }。
    """
    col_pos: dict[str, int] = {}
    for name in attrs_order:
        idx = header_line.find(" " + name + " ")
        if idx < 0:
            idx = header_line.find(name)
        if idx >= 0:
            col_pos[name] = idx
    return col_pos


def parseFixedWidthAttrs(
    line: str,
    col_pos: dict[str, int],
    attrs_order: list[str],
) -> tuple[str, dict[str, str]]:
    """
    按列位置从一行文本中解析「point 名」与各属性值。

    逻辑：按 col_pos 中列名的起始位置排序，逐列截取到下一列起始位置；值为 '-' 时视为空。
    返回 (point 名, { 列名: 值 })。
    """
    content = line.rstrip()
    ordered = sorted(
        [name for name in attrs_order if name in col_pos],
        key=lambda x: col_pos[x],
    )
    if not ordered:
        return "", {}
    point = content[: col_pos[ordered[0]]].strip()
    attrs: dict[str, str] = {}
    for i, name in enumerate(ordered):
        start = col_pos[name]
        end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(content)
        value = content[start:end].strip() if start < end else ""
        attrs[name] = "" if value == "-" else value
    for name in attrs_order:
        attrs.setdefault(name, "")
    return point, attrs


def fillUncertainty(lines: list[str], meta: dict[str, Any]) -> None:
    """
    从 path 文本中解析 clock uncertainty 行，将数值写入 meta["uncertainty"]。
    """
    key = "clock uncertainty"
    for line in lines:
        if key in line.lower():
            idx = line.lower().find(key)
            rest = line[idx + len(key) :]
            m = re.search(r"(-?\d+\.\d+)", rest)
            if m:
                meta["uncertainty"] = m.group(1).strip()
            break
    meta.setdefault("uncertainty", "")


def sumDelayInRows(rows: list[dict[str, Any]], delay_attr: str) -> float:
    """
    对行列表中指定延迟列的数值求和。

    从每行 delay_attr 的值中提取首个数字（支持负数和小数），累加后返回。
    用于计算 launch_clock / data_path 段的总延迟。
    """
    total = 0.0
    for r in rows:
        val = r.get(delay_attr)
        if val is None:
            continue
        try:
            s = str(val).strip()
            m = re.search(r"-?\d+(?:\.\d+)?", s)
            if not m:
                continue
            total += float(m.group(0))
        except (ValueError, TypeError):
            pass
    return total
