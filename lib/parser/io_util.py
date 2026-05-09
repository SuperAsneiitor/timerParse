"""
Timing 报告文本读取小工具。

职责：为解析与抽取提供统一的 UTF-8 文本打开方式；路径以 .gz 结尾时按 gzip 解压读取。
"""
from __future__ import annotations

import gzip
from typing import TextIO


def openReportText(path: str) -> TextIO:
    """
    以 UTF-8 文本方式打开 timing 报告。

    若路径（不区分大小写）以 .gz 结尾，则使用 gzip 解压读取；否则按普通文本打开。
    非法字节按 replacement 字符替换（errors='replace'）。

    返回对象应在 with 语句中使用并在块结束时关闭。
    """
    if path.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")
