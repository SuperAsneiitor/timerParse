# timerExtract

解析多种 Timing 报告格式，提取每条 path 的 launch/capture 路径点及 path 级汇总，输出 CSV；支持 PrimeTime 报告生成与 path summary 对比。

**代码与入口**：所有功能代码位于 `lib/` 目录，**统一入口**为：

```bash
python -m lib <子命令> [参数...]
```

所有子命令支持 **`-l/--log-level brief|full`**：`brief` 为每步一行汇总（默认），`full` 为多行展开（如各 CSV 路径与行数、列名等）。

**仓库中不包含测试数据与测试结果**：`input/` 及各类 `output*/` 已通过 `.gitignore` 排除。

---

## 功能一览

| 功能 | 子命令 | 输入 | 输出 | 处理过程 |
|------|--------|------|------|----------|
| **解析 Timing 报告** | `extract` | 单个 timing 报告文件（`.rpt` 等） | `launch_path.csv`、`capture_path.csv`、`launch_clock_path.csv`、`data_path.csv`、`path_summary.csv` | 按格式(format1/format2/pt) 切 path → 每 path 解析 launch/capture → 按 startpoint 将 launch 拆成 launch_clock / data_path（`launch_path.csv` 含 `path_type`）→ 汇总写 CSV；支持 `-j` 多进程 |
| **生成 PT report_timing** | `gen-pt` | `launch_path.csv`（及可选参数） | `report_timing.tcl`（含 set output_file、rm/touch、若干 report_timing 行并重定向） | 按 path_id 分组 → 每 path 用 trigger_edge 生成 -rise_through/-fall_through → 拼接 TCL；支持 `-j` |
| **对比 path_summary** | `compare` | 两个 path_summary CSV（golden + test） | 对比 CSV（完整/简化）、`compare_stats.json`、可选 `compare_stats.csv`、图表目录、`compare_report.html` | 按 path_id 对齐 → 算 (test−golden)/golden×100% → 统计（绝对值均值、3 位小数）、阈值、相关性 → 可选画图与 HTML |
| **生成 Timing 报告** | `gen-report` | YAML 配置文件 | 指定格式的 timing 报告文件（.rpt） | 按 YAML 生成每条 path 的 Title（Scenario、Path Start、Path End、Common Pin、Group Name、Analysis Type 等）与 path 表格；支持固定值、枚举、随机数、模板等取值方式，列顺序可配置 |

`path_summary.csv` 列：`path_id,startpoint,endpoint,arrival_time,required_time,clock_reconvergence_pessimism,clock_uncertainty,slack,launch_clock_point_count,data_path_point_count,capture_point_count,launch_clock_delay,data_path_delay`。

---

## 统一入口用法

### 1. 解析 Timing 报告（extract）

```bash
# 自动识别格式（兼容旧用法：首参数为文件时等价于 extract）
python -m lib path/to/report.rpt -o path/to/output
python -m lib extract path/to/report.rpt -o path/to/output

# 显式指定格式
python -m lib extract path/to/report.rpt -f format1 -o output
python -m lib extract path/to/report.rpt -f pt -o output

# 多进程解析
python -m lib extract path/to/report.rpt -o output -j 4
```

| 参数 | 说明 |
|------|------|
| `input_rpt` | Timing 报告文件路径 |
| `-o`, `--output-dir` | 输出目录，默认 `output_lib` |
| `-f`, `--format` | `auto` / `format1` / `format2` / `pt` / `apr`（默认 `auto`） |
| `-j`, `--jobs` | 并行 worker 数，默认 1 |

**输出文件**：`launch_path.csv`、`capture_path.csv`、`launch_clock_path.csv`、`data_path.csv`、`path_summary.csv`（含 launch_clock_point_count、data_path_point_count、capture_point_count、launch_clock_delay、data_path_delay）。

- `launch_path.csv` 额外包含 `path_type` 列，值为 `launch_clock` 或 `data_path`。
- `path_summary.csv` 的 `launch_clock_delay`、`data_path_delay` 写出前会做浮点清理（避免 `0.39000000000000001` 这类显示噪声）。

#### parser_chaos：分割器 + 解析器进程 + 队列

另一套**独立实现**位于 `lib/parser_chaos`，采用 1 个报告分割器进程 + N 个解析器 Worker 进程 + 队列的架构，与 `lib/parsers` 无任何引用关系。适合需要「分割与解析分离、动态分配任务」的场景。

```bash
python scripts/run_extract_chaos.py path/to/report.rpt -o output_parser_chaos --format auto -j 4
```

详见 [docs/parser_chaos.md](docs/parser_chaos.md)。跨机迁移或恢复会话上下文可参考 [docs/SESSION_MIGRATION.md](docs/SESSION_MIGRATION.md)。

---

### 2. 生成 PrimeTime report_timing（gen-pt）

```bash
python -m lib gen-pt output/launch_path.csv -o output/report_timing.tcl
python -m lib gen-pt -n 10 -w -e "-delay_type max"
python -m lib gen-pt -j 4
```

| 参数 | 说明 |
|------|------|
| `launch_csv` | launch_path.csv 路径（可选，默认 `output/launch_path.csv`） |
| `-o`, `--output` | 输出 TCL 路径 |
| `-n`, `--max-paths` | 仅生成前 N 条 path（0=全部） |
| `-w`, `--no-wrap` | 每条 report_timing 单行输出（不换行） |
| `-e`, `--extra` | 额外 report_timing 参数（原样拼到命令末尾） |
| `-r`, `--report-file` | TCL 中输出文件名变量 |
| `-j`, `--jobs` | 多进程 worker 数 |

---

### 3. 对比 path_summary（compare）

```bash
python -m lib compare -g golden/path_summary.csv -t test/path_summary.csv -o output/compare_result.csv
python -m lib compare -g golden/path_summary.csv -t test/path_summary.csv -o out.csv -T 5 -C -H

# 兼容旧用法（位置参数）
python -m lib compare golden/path_summary.csv test/path_summary.csv -o out.csv
```

| 参数 | 说明 |
|------|------|
| `-g`, `--golden-file` | Golden path_summary.csv 路径（推荐显式传参） |
| `-t`, `--test-file` | Test path_summary.csv 路径（推荐显式传参） |
| `golden_file` / `test_file` | 兼容旧用法：位置参数（可选） |
| `-o`, `--output` | 完整版对比 CSV 路径 |
| `-T`, `--threshold` | 阈值统计条件（默认 10%） |
| `-b`, `--bins` | 直方图桶数 |
| `-c`, `--charts-dir` | 图表目录 |
| `-C`, `--no-charts` / `-H`, `--no-html` | 禁用图表 / HTML 报告 |
| `-s`, `--stats-json` / `-S`, `--stats-csv` | 统计 JSON/CSV 路径 |

**输出**：完整/简化对比 CSV、`compare_stats.json`（可选 `compare_stats.csv`）、`charts/`、`compare_report.html`；比值与统计保留 3 位小数，mean 为绝对值均值。  
其中 `compare_stats.json` 与 `compare_report.html` 会显式记录输入参数 `golden_file`、`test_file`，便于追溯对比来源。

---

### 4. 生成 Timing 报告（gen-report）

通过 YAML 配置生成不同格式的 timing 报告。每条 path 的生成分为两部分：

1. **Path Title**：Scenario、Path Start、Path End、Common Pin、Group Name、Analysis Type 等；可指定属性名、值的类型（固定值、枚举、随机、模板引用）。
2. **Timing path 表格**：各列属性名与取值配置，列顺序可自定义；可按行类型（clock/pin/net/arrival/slack 等）控制某列是否输出。

```bash
# 不指定 -o 时会按格式自动写入：
#   output/gen_format2_timing_report.rpt / output/gen_format1_timing_report.rpt / output/gen_pt_timing_report.rpt
python -m lib gen-report config/gen_report/format2.yaml
python -m lib gen-report config/gen_report/format2.yaml -s 42

# 也可以显式指定输出路径
python -m lib gen-report config/gen_report/format2.yaml -o output/custom.rpt
```

| 参数 | 说明 |
|------|------|
| `config` | YAML 配置文件路径 |
| `-o`, `--output` | 输出报告文件路径；不指定时默认 `output/gen_<format>_timing_report.rpt` |
| `-s`, `--seed` | 随机种子（可复现生成结果） |

**YAML 配置要点（base + override）**：

- `format`：`format2` / `format1`（影响 title 与表头排版）。
- `num_paths`：生成的 path 条数。
- `extends`（可选）：继承基础模板（如 `config/gen_report/base.yaml`）。
- `variables`（可选）：为每条 path 预生成变量，供 title/表格中 `format` 引用，如 `startpoint`、`endpoint`、`clock`。
- `row_type_profiles`（可选）：行类型分组，列通过 `profiles` 自动映射到 `when_type`。
- `title.attributes`：列表，每项 `name` + `value`。`value` 支持：
  - `type: fixed`，`value: "字符串或数字"`
  - `type: enum`，`choices: [a, b, c]`（可加 `weights`）
  - `type: format` / `template`，`template: "{startpoint} ( ... )"`（可引用 path_vars 与 title 中已解析字段）
  - `type: ref`，`ref: 字段名`
  - `type: random_float`，`min`/`max`/`decimals`
  - `type: random_int`，`min`/`max`
- `table.column_order`：列名顺序。
- `table.columns`：列名 → `value`（同上类型）+ 可选 `when_type` 或 `profiles`。
- `structure.launch`：launch 段行序列，如 `[{ type: clock, count: 2 }, { type: pin, count: 4 }, { type: arrival, count: 1 }]`。
- `structure.capture`：capture 段行序列。
- 特殊：列 `Type` 可用 `value: { type: row_type }` 表示取当前行类型。
- **point_generator**（可选）：为每条 path 的 launch/capture 每一行生成 point 名，形成完整 timing 路径。配置后：
  - **startpoint** = launch 段中第一个 pin 行的 point 名，**endpoint** = 最后一个 pin 行的 point 名（无需在 path_vars 里再配 startpoint/endpoint）。
  - 表格中可用 `{point}` 引用当前行的生成 point 名（如 Description 列）。
  - 按行类型配置模板，如 `clock`、`net`、`pin`（pin 行可用 `{prefix}`、`{pin_index}`、`{pin_suffix}`（Q/D/Z）、`{pin_index_in_launch}` 等）。
- **table.cumulative_rules**（可选）：属性累加关系。format1/pt 默认 `Path: Incr`，format2 默认 `Time: Delay`。
- `summary_policy`（可选）：summary 固定行策略（例如 PT 的 `statistical_adjustment` 开关及 Incr/Path 值）。

三种格式与真实报告的结构对比、累加关系说明见 **docs/FORMAT_VALIDATION.md**。

三种格式示例配置见 `config/gen_report/`：
- `config/gen_report/base.yaml`
- `config/gen_report/format1.yaml`
- `config/gen_report/format2.yaml`
- `config/gen_report/pt.yaml`

#### 4.1 PT 报告对齐约定（生成 & 解析）

- **clock 行**：launch/capture 第一行的 `clock clk_hclk (rise edge)` 仅带 `Mean/Incr/Path`，**不带 `Trans/Sensit`**。  
- **clock source latency**：第二行使用文案 `clock source latency`（不再是 `clock network delay (ideal)`）。  
- **port 行（`dft_clk (in)`）**：在 `Trans, Mean, Sensit, Incr, Path` 上都有数值，用于验证端口一侧 clock 栈的行为。  
- **数值精度**：  
  - `Fanout` 为整数；  
  - `Cap, Trans, Derate, Mean, Sensit, Incr, Path` 统一保留 4 位小数（生成的 .rpt 与抽取后的 CSV 都遵守该规则）。  
- **不确定性/重收敛**：每条路径的 `clock reconvergence pessimism` 与 `clock uncertainty` 会被解析为 `path_summary.csv` 中的 `clock_reconvergence_pessimism` 与 `clock_uncertainty` 列，在 `lib extract` 与 `parser_chaos` 中保持一致（旧的 `uncertainty` 列已移除）。

#### 4.2 Format1 报告的智能解析（行类型 + 数值顺序）

- Format1 的点表列为 `Point, Fanout, Cap, Trans, Location, Incr, Path`，现在在 **lib 解析栈与 parser_chaos 中都不再依赖「列名起始位置」做定宽切分来决定数值列归属**。  
- 抽取时会先按行内容判断行类型（`clock` / `net` / `pin`），再基于「行类型 + 数值 token 顺序」映射列，例如：  
  - clock 行只映射 `Incr, Path`；  
  - net 行映射 `Fanout, Cap, Incr, Path`；  
  - pin 行映射 `Cap, Trans, Incr, Path`。  
- 这样可以兼容**列稍有错位**或外部 APR 报告中对齐不完全一致的情况，同时保证 `launch_path.csv` / `capture_path.csv` 中的数值语义与原报告一致。

#### 4.3 Format2 报告的智能解析（含 `xd` 与坐标块）

- Format2 的 net 行允许在 `Cap` 后携带修饰符（如 `0.007 xd`），解析时会按语义提取 `Fanout` 与 `Cap`，`xd` 不参与数值列。  
- pin 行支持 `Derate` 与坐标块混排（如 `0.900,0.900   {  276.893  820.681}`），解析器会先抽取 `Derate` 与 `{x y}`，再按行类型恢复 `Trans/D-Delay/Delay/Time`。  
- port 行（launch/capture 第三行）现在明确输出并解析 `Delay`、`Time`、`trigger_edge`、`Description`：  
  - `trigger_edge` 来自 `Time` 与 `Description` 之间的 ` / ` 或 ` \ `；  
  - `Description` 规范为 `<port_name> (in)`（如 `dft_clk (in)`）。  
- `lib extract` 与 `parser_chaos` 的 format2 解析规则已对齐为「行类型 + 数值 token 顺序 + 正则提取」，避免把列宽/空格漂移误判成数值截断。  
- 说明：`test_results/.../debug/launch_path.csv` 现在也输出语义化字段，不再直接 dump 定宽切片结果。

---

## 支持的报告格式

| 格式 | 说明 | 识别方式 |
|------|------|----------|
| **apr** | APR 工具报告，Point 表含 Location、Incr、Path | `Startpoint:` + `slack (VIOLATED/MET)`，表头含 Location |
| **pt** | PrimeTime 风格，Point 表含 Derate、Incr、Path（无 Location） | `Report : timing` + `Derate` + `Startpoint:` |
| **format2** | Path Start/Path End + Type–Description 表，含 x-coord/y-coord、Derate | `Path Start` / `Path End` + `slack (VIOLATED/MET)` |

使用 `--format auto` 时按文件内容自动选择格式。

---

## 解析规则（按 point 类型）

除各格式规定的「前 N 行」保留全部属性外，其余 point 按类型只保留部分列：

- **format1 (APR)**：前 2 行全量；**input_pin / output_pin** → Cap, Trans, Location, Incr, Path, trigger_edge；**net** → Fanout。
- **pt**：前 2 行全量；**input_pin / output_pin** → Trans, Derate, Mean, Sensit, Incr, Path, trigger_edge；**net** → Fanout, Cap。
- **format2**：前 4 行全量；类型由 Type 列判断，各类型保留属性见项目内说明。

**trigger_edge**：format1/pt 从 Path 末列 r/f 映射；format2 从 Time 与 Description 间 ` / ` / ` \ ` 映射为 r/f。

---

## lib 目录结构

- `lib/parsers/`：三种报告解析实现与基类
  - `lib/parsers/time_parser_base.py`：`TimeParser`、`ParseOutput`、`split_launch_by_common_pin` 等
  - `lib/parsers/format1_parser.py` / `format2_parser.py` / `pt_parser.py`
- `lib/report_gen/`：timing report 生成器（模板基类 + 三种格式子类）
  - `lib/report_gen/base.py`：`TimingReportTemplate`
  - `lib/report_gen/format1.py` / `format2.py` / `pt.py`
- `lib/extract.py`：extract 子命令逻辑（解析 + 写 CSV）
- `lib/gen_pt_report_timing.py`：gen-pt 子命令逻辑（launch_path → report_timing TCL）
- `lib/compare_path_summary.py`：compare 子命令逻辑（两个 path_summary 对比与统计）
- `lib/cli.py`：统一入口与子命令分发；`lib/__main__.py` 调用 `run_cli()`

兼容性：仍保留 `lib/format1_parser.py` 等旧模块路径作为薄包装转发到 `lib/parsers/`。

`scripts/` 下保留薄包装脚本，内部调用 `python -m lib <子命令>`，便于旧命令行习惯。

---

## 测试

```bash
python -m unittest tests.test_format1_parser tests.test_format2_parser tests.test_pt_parser tests.test_gen_pt_report_timing tests.test_compare_path_summary -v
```

**测试结果统一存放**：所有测试运行产物（extract 输出、compare 结果、gen-report 报告等）建议写入 **test_results/**，并在**文件名或子目录名中带测试时间戳**（如 `test_results/extract_20260310_143022/`）。可用脚本：

```bash
python scripts/run_tests_with_timestamp.py extract input/report.rpt
python scripts/run_tests_with_timestamp.py gen-report config/gen_report/format2.yaml
python scripts/run_tests_with_timestamp.py compare golden/path_summary.csv test/path_summary.csv
```

详见 `test_results/README.md`。`test_results/` 已加入 `.gitignore`，仅保留目录说明。

---

## 依赖

- Python 3.6+
- **gen-report**：`pyyaml`（`pip install pyyaml`）
- 可选：`matplotlib`（compare 图表；脚本会尝试自动安装）

---

## 上传 GitHub 说明

- 测试数据和测试结果**不上传**：`input/`、`output/`、`output_*/` 已加入 `.gitignore`。
- 推送时仅添加代码与文档：`git add lib/ scripts/ README.md .gitignore` 等。
