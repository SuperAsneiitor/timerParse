# APR Timing 报告解析 (timerExtract)

解析 APR 工具生成的 Timing 报告（如 `place_REG2REG.rpt`），提取每条 Timing path 的 start/end、launch path 与 capture path 上各 point 的指标（默认 Fanout、Cap、Trans），并输出为 CSV。指标名可配置，便于后续扩展新列。

## 输入

- 报告路径（默认）：`input/place_REG2REG.rpt`
- 报告结构：每条 path 从 `Startpoint:` 开始，到 `slack (VIOLATED/MET)` 结束；中间包含 Point 表（Fanout、Cap、Trans、Location、Incr、Path 等列）

## 输出

- `output/launch_path.csv`：launch（发射）路径上所有 point，含 path_id、startpoint、endpoint、时钟、slack、point_index、point 及配置的指标列（默认 fanout、cap、trans）
- `output/capture_path.csv`：capture（捕获）路径，列同上

## 用法

```bash
# 使用默认路径（项目下 input/place_REG2REG.rpt，输出到 output/）
python scripts/parse_timing_rpt.py

# 指定输入与输出目录
python scripts/parse_timing_rpt.py path/to/place_REG2REG.rpt -o path/to/output

# 大文件多进程解析（4 个 worker）
python scripts/parse_timing_rpt.py input/place_REG2REG.rpt -o output -j 4

# 指定指标列名（可扩展）
python scripts/parse_timing_rpt.py input/place_REG2REG.rpt -o output --metrics Fanout Cap Trans
```

## 参数

| 参数 | 说明 |
|------|------|
| `input_rpt` | 可选，Timing 报告文件路径，默认 `input/place_REG2REG.rpt` |
| `-o`, `--output-dir` | 输出目录，默认 `output` |
| `-j`, `--jobs` | 并行 worker 数，默认 1；path 数 &lt; 100 时自动改为 1 |
| `--metrics` | Point 表指标列名，默认 Fanout Cap Trans；可扩展。运行时会打印：Point metrics: Fanout, Cap, Trans |

## 生成 PrimeTime report_timing 脚本

在解析得到 `launch_path.csv` 后，可用 `gen_pt_report_timing.py` 生成 PT 的 `report_timing` TCL。运行时会打印 CSV 中的指标列名（如 fanout, cap, trans）。

- **输入 pin**（如 A1, A2, CK, D, I）→ `-rise_through`
- **输出 pin**（如 Q, Z, ZN）→ `-fall_through`
- 网络 `(net)`、虚拟点（如 clock、data arrival time）不写入 through 列表

```bash
# 默认：从 output/launch_path.csv 生成 output/report_timing.tcl
python scripts/gen_pt_report_timing.py

# 指定输入 CSV 与输出 TCL
python scripts/gen_pt_report_timing.py output/launch_path.csv -o output/report_timing.tcl

# 只生成前 N 条 path（便于调试）
python scripts/gen_pt_report_timing.py -n 10

# 单行输出（不换行）
python scripts/gen_pt_report_timing.py --no-wrap
```

# 额外参数
python scripts/gen_pt_report_timing.py -extra "delay_type max"

生成示例（每条 path 一条 `report_timing`，默认带换行）：

```tcl
# path_id 1
report_timing -from {startpoint/inst/Q} -to {endpoint/inst/D} \
  -rise_through {inst1/A2 (AND2...)} \
  -fall_through {inst1/Z (AND2...)} \
  ...
```

## 依赖

- Python 3.6+

无需额外第三方库。
