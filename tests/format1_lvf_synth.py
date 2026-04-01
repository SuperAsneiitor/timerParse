# -*- coding: utf-8 -*-
"""合成 format1 LVF 报告文本（双层表头 + 三元组列），支持长 data_path（launch 段多组 pin/net）。"""
from __future__ import annotations

# 与 gen-report 中 base.yaml 的随机区间同量级：长路径至少含若干组 timing group
DEFAULT_EXTRA_DATA_GROUPS = 4
# 与 config/gen_report/format1.yaml 中 propagated_port 默认一致
DEFAULT_PROPAGATED_PORT = "pll_cpu_clk"

_F1_LVF_COLS = [
    "Point",
    "Fanout",
    "Derate",
    "Cap",
    "DTrans",
    "TransMean",
    "TransSensit",
    "TransValue",
    "Location",
    "Delta",
    "IncrMean",
    "IncrSensit",
    "IncrValue",
    "PathMean",
    "PathSensit",
    "PathValue",
]
_F1_LVF_WIDTHS = {
    "Point": 140,
    "Fanout": 8,
    "Derate": 14,
    "Cap": 10,
    "DTrans": 10,
    "TransMean": 9,
    "TransSensit": 9,
    "TransValue": 9,
    "Location": 24,
    "Delta": 9,
    "IncrMean": 9,
    "IncrSensit": 9,
    "IncrValue": 9,
    "PathMean": 9,
    "PathSensit": 9,
    "PathValue": 9,
}
_F1_LVF_SEP = "-" * max(80, 2 + sum(_F1_LVF_WIDTHS[c] for c in _F1_LVF_COLS))


def _f1_lvf_row(*cells: str) -> str:
    parts = ["  "]
    for i, col in enumerate(_F1_LVF_COLS):
        w = int(_F1_LVF_WIDTHS[col])
        text = cells[i] if i < len(cells) else ""
        parts.append(str(text).ljust(w)[:w])
    return "".join(parts).rstrip()


def _f1_lvf_header_line() -> str:
    return _f1_lvf_row(
        "",
        "",
        "",
        "",
        "",
        "-Trans-",
        "",
        "",
        "",
        "",
        "-Incr-",
        "",
        "",
        "-Path-",
        "",
        "",
    )


def _f1_lvf_sub_header_line() -> str:
    return _f1_lvf_row(
        "Point",
        "Fanout",
        "Derate",
        "Cap",
        "DTrans",
        "Mean",
        "Sensit",
        "Value",
        "Location",
        "Delta",
        "Mean",
        "Sensit",
        "Value",
        "Mean",
        "Sensit",
        "Value",
    )


def _lvf_pin_like_row(
    point: str,
    *,
    derate: str = "0.8766:1.1000",
    path_tail: str = " r",
) -> str:
    """典型 input/output pin 行（LVF 列填满，PathValue 末位可带 r/f）。"""
    return _f1_lvf_row(
        point,
        "1",
        derate,
        "0.0080",
        "0.0000",
        "0.0450",
        "0.000",
        "0.0450",
        "(522.4000, 695.8100)",
        "0.0000",
        "0.0450",
        "0.000",
        "0.0450",
        "0.1460",
        "0.0260",
        f"0.1460{path_tail}",
    )


def _lvf_clock_family_row(point: str, *, path_mean: str = "0.1460") -> str:
    """clock / clock source latency 等非 pin 行（与首行 clock 同列占位风格）。"""
    return _f1_lvf_row(
        point,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "0.0450",
        "",
        "",
        path_mean,
    )


def _lvf_port_propagated_row(port_name: str) -> str:
    """propagated port 行：Point 为「{port} （propagated)」，Location 置「-」（对齐 format1 生成器语义）。"""
    point = f"{port_name}  （propagated)"
    return _f1_lvf_row(
        point,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "-",
        "",
        "",
        "",
        "",
        "0.0450",
        "",
        "",
        "0.1460",
    )


def _lvf_net_row(point: str) -> str:
    return _f1_lvf_row(
        point,
        "2",
        "",
        "0.0080",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "0.1460",
        "0.0100",
        "0.1560",
    )


def buildFormat1LvfSinglePathBlock(path_index: int, extra_data_groups: int = DEFAULT_EXTRA_DATA_GROUPS) -> str:
    """
    构造单条 path 的 LVF 报告块（含 Startpoint…slack）。

    path_index：1-based。
    extra_data_groups：startpoint（首颗 output pin）之后，再追加多少组 (input_pin, output_pin, net)，
    用于拉长 **data_path**（与 launch_clock 分界仍由 Startpoint 与 splitLaunchByCommonPin 决定）。

    结构要点：
    - Startpoint 必须与 launch 段中**第一条作为起点的 output pin** 文本一致（归一化后匹配），
      否则整条 launch 会被算入 launch_clock，data_path 为空。
    - launch_clock：与 gen-report format1 一致 — clock → clock source latency → propagated port → 时钟网络 pin（如 ibuf/CK）→ …
    - data_path：从 Startpoint 对应行起，到 data arrival 之前的所有点行。
    """
    n = path_index
    prefix = f"x_ct_top_0/path_{n}"
    sp = f"{prefix}/reg_sp/Q"
    ep = f"{prefix}/reg_ep/D"
    # 标题行用与点表一致的实例/引脚名（无括号或 parser 会归一化）
    lines_launch: list[str] = []

    lines_launch.append(_lvf_clock_family_row("clock CORECLK (rise edge)"))
    lines_launch.append(_lvf_clock_family_row("clock source latency"))
    lines_launch.append(_lvf_port_propagated_row(DEFAULT_PROPAGATED_PORT))
    # launch_clock：时钟网络侧 input（与 Startpoint 不同）
    lines_launch.append(_lvf_pin_like_row(f"{prefix}/ibuf/CK (BUF)", path_tail=" r"))
    # Startpoint 行：必须与 header 中 Startpoint 一致 → data_path 起点
    lines_launch.append(_lvf_pin_like_row(f"{sp} (DSNQV2S_96S6T16UL)", path_tail=" r"))

    for g in range(extra_data_groups):
        lines_launch.append(_lvf_pin_like_row(f"{prefix}/dp_u{g}/I (BUF)", path_tail=" r"))
        lines_launch.append(_lvf_pin_like_row(f"{prefix}/dp_u{g}/Z (BUF)", path_tail=" f"))
        lines_launch.append(_lvf_net_row(f"{prefix}/n{g} (net)"))

    lines_launch.append(
        _f1_lvf_row(
            "data arrival time",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "0.5750",
        )
    )

    launch_body = "\n".join(lines_launch)

    pin_z = f"{prefix}/u1/Z (BUF)"
    capture_lines = [
        _lvf_clock_family_row("clock CORECLK (rise edge)", path_mean="0.0190"),
        _lvf_clock_family_row("clock source latency", path_mean="0.0190"),
        _lvf_port_propagated_row(DEFAULT_PROPAGATED_PORT),
        _f1_lvf_row(
            pin_z,
            "1",
            "0.8000:0.9000",
            "0.0040",
            "0.0000",
            "0.0420",
            "0.000",
            "0.0420",
            "(237.7400, 833.8600)",
            "0.0000",
            "0.0450",
            "0.000",
            "0.0450",
            "0.1930",
            "0.0470",
            "0.1930 f",
        ),
        _f1_lvf_row(
            "library setup time",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "-0.0190",
            "",
            "",
            "-0.0190",
        ),
        _f1_lvf_row(
            "data required time",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "0.8000",
        ),
        _f1_lvf_row(
            "slack (MET)",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "0.2250",
        ),
    ]
    capture_body = "\n".join(capture_lines)

    return rf"""
sta.timing_check_type: setup
  Startpoint: {sp} (falling edge-triggered flip-flop clocked by CORECLK)
  Endpoint: {ep} (rising edge-triggered flip-flop clocked by CORECLK)
  Scenario: demo

{_f1_lvf_header_line()}
{_f1_lvf_sub_header_line()}
{_F1_LVF_SEP}
{launch_body}

{capture_body}
""".lstrip("\n")


def buildFormat1LvfReport(num_paths: int, extra_data_groups: int = DEFAULT_EXTRA_DATA_GROUPS) -> str:
    """拼接 num_paths 条独立 path（每条以 Startpoint 开头、slack 行结束）。"""
    if num_paths < 1:
        return ""
    parts = [buildFormat1LvfSinglePathBlock(i, extra_data_groups=extra_data_groups) for i in range(1, num_paths + 1)]
    return "\n\n".join(parts)
