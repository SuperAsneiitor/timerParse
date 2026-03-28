"""parser_V2 分词与基础提取工具。"""
from __future__ import annotations

import re

_RE_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def split_tokens(line: str) -> list[str]:
    """按空白切分 token。"""
    return (line or "").strip().split()


def extract_tail_numbers(line: str, count: int) -> list[str]:
    """提取行尾 count 个数值。"""
    nums = _RE_NUM.findall(line or "")
    if count <= 0 or not nums:
        return []
    if len(nums) <= count:
        return nums
    return nums[-count:]


def text_after_last_number(line: str) -> str:
    """取最后一个数值 token 后面的文本。"""
    tokens = split_tokens(line)
    last_num = -1
    for i in range(len(tokens) - 1, -1, -1):
        if _RE_NUM.fullmatch(tokens[i]):
            last_num = i
            break
    if last_num < 0:
        return " ".join(tokens).strip()
    return " ".join(tokens[last_num + 1 :]).strip()


def normalize_point_text(text: str) -> str:
    """清理 point 前导符号与坐标残留。"""
    s = (text or "").strip()
    if s.startswith("/ "):
        s = s[2:].strip()
    if s.startswith("\\ "):
        s = s[2:].strip()
    while s and s[0] in " {}0123456789.-":
        s = s[1:].lstrip()
    return s
