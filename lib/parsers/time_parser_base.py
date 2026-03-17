"""
Timing 报告解析基类与通用数据结构。

本模块提供解析链路中的抽象基类 TimeParser 与解析结果容器 ParseOutput。
职责：定义单 path 解析接口（scanPathBlocks、parseOnePath）、launch 段按 common pin 拆分、
固定列宽解析与 CSV 写出；不读报告文件以外的 I/O，由 extract 层负责编排与写文件。
"""
from __future__ import annotations

import csv
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ParseOutput:
    """解析结果容器。launch 按 common pin（startpoint）拆分为 launch_clock 与 data_path。"""

    launch_rows: list[dict[str, Any]]
    capture_rows: list[dict[str, Any]]
    summary_rows: list[dict[str, Any]]
    launch_clock_rows: list[dict[str, Any]]
    data_path_rows: list[dict[str, Any]]


class TimeParser(ABC):
    """
    Timing report 解析抽象基类（模板方法）。

    子类实现 scanPathBlocks（按 path 分块）、parseOnePath（单块解析）；
    本类提供 launch 按 startpoint 拆分、列位置提取、固定列宽解析、类型过滤与 CSV 写出。
    """

    default_attrs_order: list[str] = []
    skip_first_rows: int = 0
    default_attrs_by_type: dict[str, list[str]] = {}

    def __init__(
        self,
        attrs_order: list[str] | None = None,
        attrs_by_type: dict[str, list[str]] | None = None,
    ) -> None:
        self.attrs_order = attrs_order[:] if attrs_order else self.default_attrs_order[:]
        self.attrs_by_type = (
            {k: v[:] for k, v in attrs_by_type.items()}
            if attrs_by_type
            else {k: v[:] for k, v in self.default_attrs_by_type.items()}
        )

    @property
    def point_base_columns(self) -> list[str]:
        """点表 CSV 的公共列（path_id、startpoint、endpoint、point 等）。"""
        return [
            "path_id",
            "startpoint",
            "endpoint",
            "startpoint_clock",
            "endpoint_clock",
            "slack",
            "slack_status",
            "point_index",
            "point",
        ]

    @property
    def summary_columns(self) -> list[str]:
        """path_summary 表列（每条 path 一行）。"""
        return [
            "path_id",
            "startpoint",
            "endpoint",
            "arrival_time",
            "required_time",
            "clock_reconvergence_pessimism",
            "clock_uncertainty",
            "slack",
            "launch_clock_point_count",
            "data_path_point_count",
            "capture_point_count",
            "launch_clock_delay",
            "data_path_delay",
        ]

    @staticmethod
    def _fillUncertainty(lines: list[str], meta: dict[str, Any]) -> None:
        """从 path 文本中解析 reconvergence/uncertainty，并兼容保留 uncertainty 别名列。
        PT/format1：关键词在行首，数值在关键词后（Incr/Path），取倒数第二个为 Incr。
        format2：关键词在行尾 Description，数值在关键词前（Delay/Time），从行首取倒数第二个为 Delay。
        """
        def _extractIncrementKeyword(line_text: str, keyword: str) -> str:
            low = line_text.lower()
            idx = low.find(keyword)
            if idx < 0:
                return ""
            # 关键词后的部分（PT/format1：Incr, Path 等）
            rest = line_text[idx + len(keyword) :]
            nums_after = re.findall(r"-?\d+(?:\.\d+)?", rest)
            if nums_after:
                return nums_after[-2] if len(nums_after) >= 2 else nums_after[0]
            # 关键词前取数（format2：Delay, Time 在 Description 左侧）
            prefix = line_text[:idx]
            nums_before = re.findall(r"-?\d+(?:\.\d+)?", prefix)
            if not nums_before:
                return ""
            return nums_before[-2] if len(nums_before) >= 2 else nums_before[-1]
        reconv = ""
        uncertainty = ""
        for line in lines:
            low = line.lower()
            if not reconv and "clock reconvergence pessimism" in low:
                reconv = _extractIncrementKeyword(line, "clock reconvergence pessimism")
            if not uncertainty and "clock uncertainty" in low:
                uncertainty = _extractIncrementKeyword(line, "clock uncertainty")
            if reconv and uncertainty:
                break
        meta["clock_reconvergence_pessimism"] = reconv
        meta["clock_uncertainty"] = uncertainty

    @staticmethod
    def _normalizePin(pin: str) -> str:
        """归一化 pin 显示：去掉末尾 '<-' 与括号内的 (CELL_TYPE)。"""
        if not pin:
            return ""
        s = pin.strip()
        if s.endswith("<-"):
            s = s[:-2].strip()
        if " (" in s:
            s = s.split(" (", 1)[0].strip()
        return s

    @staticmethod
    def _cleanMetricFloat(v: float, ndigits: int = 6) -> float:
        """消除浮点累计噪声，避免 CSV 中出现 0.39000000000000001 这类显示。"""
        return round(float(v), ndigits)

    @classmethod
    def splitLaunchByCommonPin(
        cls,
        launch_rows: list[dict[str, Any]],
        startpoint: str,
        delay_attr: str = "Incr",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, float, float]:
        """
        按 startpoint 将 launch 段拆为 launch_clock 与 data_path。

        兼容 PT 原始报告：Startpoint 可能仅为实例名（如 u_logic/Uu73z4_reg），
        launch 点为具体 pin（如 u_logic/Uu73z4_reg/Q）；startpoint 所在行归入 data_path。
        返回 (launch_clock_rows, data_path_rows, lc_count, dp_count, lc_delay, dp_delay)。
        """
        target = cls._normalizePin(startpoint)
        launch_clock: list[dict[str, Any]] = []
        data_path: list[dict[str, Any]] = []
        found = False
        output_pin_suffixes = ("/Q", "/Z", "/ZN", "/ZP", "/QN", "/QB")
        for row in launch_rows:
            pt = (row.get("point") or "").strip()
            norm_pt = cls._normalizePin(pt)
            is_target_row = (
                norm_pt == target
                or (target and norm_pt.startswith(target + "/"))
            )
            is_startpoint_output = is_target_row and any(norm_pt.endswith(suf) for suf in output_pin_suffixes)
            if not found and (norm_pt == target or is_startpoint_output):
                found = True
                row["path_type"] = "data_path"
                data_path.append(row)
                continue
            if not found:
                row["path_type"] = "launch_clock"
                launch_clock.append(row)
            else:
                row["path_type"] = "data_path"
                data_path.append(row)

        lc_delay = cls._sumDelayInRows(launch_clock, delay_attr)
        dp_delay = cls._sumDelayInRows(data_path, delay_attr)
        return launch_clock, data_path, len(launch_clock), len(data_path), lc_delay, dp_delay

    @classmethod
    def _sumDelayInRows(cls, rows: list[dict[str, Any]], delay_attr: str) -> float:
        """对行列表中 delay_attr 列求和（从字符串中提取首个数值）。"""
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

    def parseReport(self, report_path: str) -> ParseOutput:
        """
        解析整份报告：扫描 path 块，逐块解析后合并 launch/capture/summary，
        并对每条 path 的 launch 按 startpoint 拆分为 launch_clock 与 data_path。
        """
        blocks = self.scanPathBlocks(report_path)
        launch_rows: list[dict[str, Any]] = []
        capture_rows: list[dict[str, Any]] = []
        launch_clock_rows: list[dict[str, Any]] = []
        data_path_rows: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []
        delay_attr = "Incr" if "Incr" in self.attrs_order else "Delay"

        for path_id, path_text in blocks:
            meta, launch, capture = self.parseOnePath(path_id, path_text)
            lc, dp, lc_n, dp_n, lc_delay, dp_delay = self.splitLaunchByCommonPin(
                launch, meta.get("startpoint", ""), delay_attr=delay_attr
            )
            meta["launch_clock_point_count"] = lc_n
            meta["data_path_point_count"] = dp_n
            meta["capture_point_count"] = len(capture)
            meta["launch_clock_delay"] = self._cleanMetricFloat(lc_delay)
            meta["data_path_delay"] = self._cleanMetricFloat(dp_delay)
            summary_rows.append(meta)
            launch_rows.extend(launch)
            launch_clock_rows.extend(lc)
            data_path_rows.extend(dp)
            capture_rows.extend(capture)

        return ParseOutput(
            launch_rows,
            capture_rows,
            summary_rows,
            launch_clock_rows,
            data_path_rows,
        )

    @abstractmethod
    def scanPathBlocks(self, report_path: str) -> list[tuple[int, str]]:
        """扫描报告文件，返回 [(path_id, path_text), ...]。"""
        ...

    @abstractmethod
    def parseOnePath(
        self, path_id: int, path_text: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """解析单条 path 文本，返回 (meta, launch_rows, capture_rows)。"""
        ...

    def buildPointRow(
        self,
        meta: dict[str, Any],
        point_index: int,
        point: str,
        attrs: dict[str, Any],
    ) -> dict[str, Any]:
        """根据 meta 与当前点属性构建一行点表数据。"""
        row = {
            "path_id": meta["path_id"],
            "startpoint": meta["startpoint"],
            "endpoint": meta["endpoint"],
            "startpoint_clock": meta["startpoint_clock"],
            "endpoint_clock": meta["endpoint_clock"],
            "slack": meta["slack"],
            "slack_status": meta["slack_status"],
            "point_index": point_index,
            "point": point,
        }
        for name in self.attrs_order:
            row[name] = attrs.get(name, "")
        return row

    def applyTypeFilter(
        self,
        attrs: dict[str, Any],
        point_type: str,
        segment_row_index: int,
    ) -> dict[str, Any]:
        """按 point_type 与 segment_row_index 过滤属性：前 skip_first_rows 行及非允许列置空。"""
        out = {name: attrs.get(name, "") for name in self.attrs_order}
        if segment_row_index < self.skip_first_rows:
            return out
        allowed = self.attrs_by_type.get(point_type)
        if not allowed:
            return out
        allowed_set = set(allowed)
        for name in self.attrs_order:
            if name not in allowed_set:
                out[name] = ""
        return out

    @staticmethod
    def extractColumnPositions(header_line: str, attrs_order: list[str]) -> dict[str, int]:
        """从表头行解析各列名起始位置（固定列宽解析用）。"""
        col_pos: dict[str, int] = {}
        for name in attrs_order:
            idx = header_line.find(" " + name + " ")
            if idx < 0:
                idx = header_line.find(name)
            if idx >= 0:
                col_pos[name] = idx
        return col_pos

    @staticmethod
    def parseFixedWidthAttrs(
        line: str,
        col_pos: dict[str, int],
        attrs_order: list[str],
    ) -> tuple[str, dict[str, str]]:
        """按列位置从一行中解析 point 名与各属性值；'-' 视为空。"""
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

    def writeCsv(self, output_path: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
        """将行数据按列顺序写出为 CSV（UTF-8 BOM，无额外空行）。"""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
