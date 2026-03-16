"""
统一日志工具：支持「简介」「完整」两档等级，用于过程输出。

- 简介 (brief)：每个子步骤只输出一行汇总。
- 完整 (full)：同一子步骤多行展开（如每个 CSV 单独一行、列名等）。
- error(msg)：始终输出到 stderr，与等级无关。
"""
from __future__ import annotations

import sys
from enum import Enum


class LogLevel(Enum):
    """日志等级：简介 / 完整。"""
    BRIEF = "brief"
    FULL = "full"


_current_level: LogLevel = LogLevel.BRIEF


def get_level() -> LogLevel:
    """返回当前日志等级。"""
    return _current_level


def set_level(level: str | LogLevel) -> None:
    """设置当前日志等级。level 可为 'brief' | 'full' 或 LogLevel。"""
    global _current_level
    if isinstance(level, LogLevel):
        _current_level = level
    else:
        s = (level or "").strip().lower()
        _current_level = LogLevel.FULL if s == "full" else LogLevel.BRIEF


def brief(msg: str) -> None:
    """简介/汇总类：仅当等级为 BRIEF 或 FULL 时向 stdout 打印（始终打印）。"""
    print(msg, flush=True)


def full(msg: str) -> None:
    """完整/明细类：仅当等级为 FULL 时向 stdout 打印。"""
    if _current_level == LogLevel.FULL:
        print(msg, flush=True)


def error(msg: str) -> None:
    """错误/警告：始终向 stderr 打印。"""
    print(msg, file=sys.stderr, flush=True)
