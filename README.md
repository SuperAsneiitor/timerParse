# timerExtract

解析多种 Timing 报告格式，提取每条 path 的 launch/capture 路径点及 path 级汇总，输出 CSV；支持 PrimeTime 报告生成与 path summary 对比。

**仓库中不包含测试数据与测试结果**：`input/` 目录及各类 `output*/` 输出目录已通过 `.gitignore` 排除，上传 GitHub 时不会包含。

---

## 功能概览

| 模块/脚本 | 作用 |
|------|------|
| `lib/` | **重构后的解析库**：`TimeParser` 抽象类 + `format1/format2/pt` 三个子类 + CLI |
| `python -m lib` | 使用新架构解析 Timing 报告并输出 CSV |
| `scripts/parse_timing_rpt.py` | 旧入口（兼容保留） |
| `scripts/gen_pt_report_timing.py` | 根据 launch_path CSV 生成 PrimeTime `report_timing` TCL |
| `scripts/compare_path_summary.py` | 对比两个 path_summary CSV（golden vs test），输出比值结果 |

---

## 支持的报告格式

| 格式 | 说明 | 识别方式 |
|------|------|----------|
| **apr** | APR 工具报告，Point 表含 Location、Incr、Path | `Startpoint:` + `slack (VIOLATED/MET)`，表头含 Location |
| **pt** | PrimeTime 风格，Point 表含 Derate、Incr、Path（无 Location） | `Report : timing` + `Derate` + `Startpoint:` |
| **format2** | Path Start/Path End + Type–Description 表，含 x-coord/y-coord、Derate | `Path Start` / `Path End` + `slack (VIOLATED/MET)` |

使用 `--format auto` 时会按文件内容自动选择格式。

---

## 解析规则（按 point 类型）

除各格式规定的「前 N 行」保留全部属性外，其余 point 按类型只保留部分列：

- **format1 (APR)**：前 2 行全量；**input_pin / output_pin** → Cap, Trans, Location, Incr, Path, trigger_edge；**net** → Fanout。
- **pt**：前 2 行全量；**input_pin / output_pin** → Trans, Incr, Path, trigger_edge；**net** → Fanout, Cap。
- **format2**：前 4 行全量；类型由 Type 列判断，各类型保留属性如下：
  - **input_pin**：D-Trans, Trans, Derate, x-coord, y-coord, D-Delay, Delay, Time, trigger_edge, Description（Time 与 Description 间可有 `/` 或 `\`）。
  - **output_pin**：Trans, Derate, x-coord, y-coord, Delay, Time, trigger_edge, Description。
  - **net**：Fanout, Cap, Description（Cap 后可能跟 `xd`）。
  - **clock**：Delay, Time, Description。
  - **port**：Trans, x-coord, y-coord, Delay, Time, Description（Time 与 Description 间可有 `/` 或 `\`）。
  - **constraint**：Delay, Time, Description。
  - **required**：Time, Description。
  - **arrival**：Time, Description。
  - **slack**：Time, Description。

Point 类型通过名称判断：含 `(net)` 为 net；pin 名为 Q/Z/ZN/ZP 为 output_pin，否则为 input_pin（format1/pt）；format2 以 Type 列为准。

**trigger_edge 规则**：
- **format1 / pt**：input/output pin 的 `Path` 最后一列 `r/f` 分别映射为 `trigger_edge=r/f`。
- **format2**：input/output pin 在 `Time` 与 `Description` 之间若为 ` / ` 则 `trigger_edge=r`，若为 ` \ ` 则 `trigger_edge=f`。

**format1 兼容说明**：点表中 launch/capture 段起始通过 `clock <clock_name> [(rise|fall edge)]` 行识别（有些报告 capture 段可能只有 `clock CORE_CLK`，不带 rise/fall edge）。为避免误把 `clock network delay (propagated)` 等描述行当作段起点，解析器要求 clock 名（及可选 edge 描述）后需直接进入数值列。`clock_name` 不再假设为固定值（例如不固定为 `CPU_CLK`）。Startpoint/Endpoint 括号中的触发沿文本可能为 `rising edge-triggered`、`falling edge-triggered` 或 `falling rising edge-triggered` 等，解析时以 `clocked by <clock>` 为准提取时钟名。

**format2 兼容说明**：若报告中 Derate 列与坐标连写（如 `0.900,0.900{219.156,772.737}`），解析器会自动拆成 Derate 与 x-coord、y-coord，避免坐标误入 Derate 列。pin/port 的 Description 按行内 ` / ` 或 ` \ ` 取整段，避免 point 名被列宽截断。

---

## 1. 重构后推荐用法（lib）

### 架构说明

- `lib/time_parser_base.py`：`TimeParser` 抽象基类（模板方法）。
- `lib/format1_parser.py`：`Format1Parser`，解析 APR/format1。
- `lib/format2_parser.py`：`Format2Parser`，解析 Path Start/Path End 风格。
- `lib/pt_parser.py`：`PtParser`，解析 PT 风格。
- `lib/cli.py` + `lib/__main__.py`：命令行入口，支持 `python -m lib`。
- `tests/test_format2_parser.py`：format2 解析与 point 名称、y-coord、Derate 拆分、trigger_edge 的单元/集成测试。
- `tests/test_format1_parser.py` / `tests/test_pt_parser.py`：format1/pt 解析、clock 识别与 trigger_edge 测试。
- `tests/test_gen_pt_report_timing.py`：report_timing 转换脚本对 trigger_edge 的参数映射测试。

### CLI 用法（推荐）

```bash
# 自动识别格式并解析
python -m lib path/to/report.rpt -o path/to/output

# 显式指定格式
python -m lib path/to/report.rpt --format format1 -o output
python -m lib path/to/report.rpt --format format2 -o output
python -m lib path/to/report.rpt --format pt -o output
```

### CLI 参数

| 参数 | 说明 |
|------|------|
| `input_rpt` | Timing 报告文件路径 |
| `-o`, `--output-dir` | 输出目录，默认 `output_lib` |
| `--format` | `auto` / `format1` / `format2` / `pt` / `apr`（默认 `auto`） |

### 输出文件

- `launch_path.csv`
- `capture_path.csv`
- `path_summary.csv`（列为 `path_id,startpoint,endpoint,arrival_time,required_time,slack`）

### 测试

```bash
python -m unittest tests.test_format1_parser tests.test_format2_parser tests.test_pt_parser tests.test_gen_pt_report_timing -v
```

---

## 2. 旧脚本用法（兼容保留）

### 输出文件

- **launch_path.csv** / **capture_path.csv**：每条 path 的 launch/capture 路径上各 point 一行，列含 path_id、startpoint、endpoint、时钟、slack、point_index、point 及该格式的属性列（如 Fanout, Cap, Trans, Incr, Path 等）。
- **path_summary.csv**：每条 path 一行，列为 `path_id, startpoint, endpoint, arrival_time, required_time, slack`（不含 trans/cap）。

### 用法

```bash
# 指定输入报告与输出目录（格式自动检测）
python scripts/parse_timing_rpt.py path/to/report.rpt -o path/to/output

# 指定格式
python scripts/parse_timing_rpt.py report.rpt -o output --format apr   # apr | pt | format2 | auto

# 多进程（path 数 ≥100 时生效）
python scripts/parse_timing_rpt.py report.rpt -o output -j 4

# 自定义 Point 表指标列名（与报告表头一致）
python scripts/parse_timing_rpt.py report.rpt -o output --metrics Fanout Cap Trans
```

### 参数

| 参数 | 说明 |
|------|------|
| `input_rpt` | Timing 报告文件路径 |
| `-o`, `--output` | 输出目录，默认 `output` |
| `--format` | `apr` / `pt` / `format2` / `auto`（默认） |
| `-j`, `--jobs` | 并行 worker 数；path 数 &lt; 100 时自动为 1 |
| `--metrics` | Point 表指标列名，默认 Fanout Cap Trans |

---

## 3. 生成 PrimeTime report_timing

根据 `launch_path.csv` 生成 PT 的 `report_timing` TCL：通过 `trigger_edge` 决定 through 参数（`r -> -rise_through`，`f -> -fall_through`），net 与虚拟点不写入。若 CSV 无 `trigger_edge` 列，脚本回退到旧规则（按 pin 名判断输出脚）。

脚本会在生成的 tcl 开头加入：
- `set output_file "report_file.rpt"`
- `sh rm -rf ${output_file}`
- `sh touch ${output_file}`

并在每条 `report_timing` 命令末尾追加：`>> ${output_file}`。

```bash
# 默认：output/launch_path.csv → output/report_timing.tcl
python scripts/gen_pt_report_timing.py

# 指定 CSV 与输出 TCL
python scripts/gen_pt_report_timing.py output/launch_path.csv -o output/report_timing.tcl

# 只生成前 N 条 path
python scripts/gen_pt_report_timing.py -n 10

# 单行输出、附加参数
python scripts/gen_pt_report_timing.py --no-wrap -extra "delay_type max"
```

---

## 4. 对比 path_summary

对比两个 path_summary CSV（golden vs test），按相同 `path_id` 计算 **arrival_time、required_time、slack** 的比值：`(test - golden) / golden`。

```bash
# 输出：完整版 compare_result.csv + 简化版 compare_result_simple.csv（仅 path_id 与三列 ratio）
python scripts/compare_path_summary.py golden/path_summary.csv test/path_summary.csv -o output/compare_result.csv
```

- **完整版**：path_id, startpoint, endpoint, 各指标的 golden/test/ratio。
- **简化版**：path_id, arrival_time_ratio, required_time_ratio, slack_ratio（文件名自动加 `_simple`）。

---

## 依赖

- Python 3.6+  
- 无第三方库

---

## 上传 GitHub 说明

- 测试数据和测试结果**不上传**：`input/` 目录及所有解析/对比输出目录已加入 `.gitignore`。
- 仓库中仅保留脚本、README 与配置文件；克隆后需自行准备 Timing 报告并指定 `-o` 输出目录运行。

**推送到 master 分支**（不包含测试数据与测试结果，已由 `.gitignore` 排除 `input/`、`output/`、`output_*/`）：

```bash
git remote add origin https://github.com/<你的用户名>/timerExtract.git   # 仅首次
git add lib/ scripts/ README.md .gitignore   # 只添加代码与文档，避免 input/output
git status   # 确认无 input/、output/、output_* 被加入
git commit -m "feat: lib TimeParser + format1/format2/pt + CLI; docs: format2 type rules"
git push -u origin master
```
