# Release Notes

## [Unreleased] - 文档与架构同步（2026-03-28）

### 概要
- **解析**：统一在 **`lib/parser_V2`**（`TimeParser` 子类 + `create_timing_report_parser`）；删除 **`lib/parsers/`** 及根目录 `lib/format1_parser.py` 等薄转发。
- **extract-chaos**：Worker 使用与 **`extract`** 相同的 **parser_V2**；移除 chaos 内重复的 `parser_format*.py` / `utils.py`；CSV 列与 `path_summary` 与 **`TimeParser.summary_columns`** 对齐。
- **实验包**：删除 **`lib/parser_chaos_V2/`** 及 `tests/test_parser_chaos_v2.py`。
- **文档**：重建 **`README.md`**（UTF-8 简体中文）；新增 **`docs/ARCHITECTURE.md`**；更新 **`docs/parser_chaos.md`**、**`PARSE_LAYOUTS.md`**、**`README_legacy.md`**、**`SESSION_MIGRATION.md`**、**`FORMAT_VALIDATION.md`**、**`PT_REPORT_REUSE_TEMPLATE.md`**。
- **格式2**：net 行 Cap 后单位 **`xf`** 与 **`xd`** 同样从描述中剥离（与 extract/chaos 行为一致）。

---

## [1.0.0] - 2026-03-19

### 更新时间
- **日期**：2026-03-19

### 更新原因与概要
- 发布 1.0.0 版本：compare 与 parser_chaos 流程进一步产品化，支持 HTML 静态分页 drill-down，以及统一 CLI 接入口与 csh `lake` 命令入口。

### 变更
- compare（path_summary 对比）增强：
  - 首页路径列表改为方案 B：关键差异列 + 默认按排序字段（默认 `slack_ratio` 的绝对值）降序。
  - 新增静态分页：`compare_report.html` + `pages/page_*.html`（默认每页 100 条）。
  - 逐点详情 drill-down：可选生成 `paths/path_*.html`（默认仅首批生成以避免 path 太多导致极慢）。
  - 新增 compare 参数：
    - `--page-size`
    - `--sort-by`
    - `--no-sort-abs`
    - `--detail-scope`

- parser_chaos CLI 集成：
  - `lib/cli.py` 新增子命令 `extract-chaos`，内部调用 `lib.parser_chaos.runExtractChaos`。
  - 默认输出目录：`output_parser_chaos`（与原脚本一致）。

- 产品命令入口：
  - 新增 `tools/lake/`：
    - `tools/lake/bin/lake`：`#!/bin/csh -f` 可执行入口，转发到 `python -m lib`。
    - `tools/lake/lake.csh`：source 脚本，注入 `LAKE_PYTHON` 与 `lake` 命令。

### 文档与测试
- `README.md` 更新 compare / extract-chaos / lake 的用法与参数说明。
- compare 单测与全链路验证流程均已通过（含 validation flow）。  

---

## [0.4.2] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 根据使用反馈，统计均值调整为按绝对值计算，并将输出精度统一为小数点后 3 位，便于阅读与对齐。

### 变更

- `compare_stats` 中 `mean` 改为 `fmean(abs(ratio_percent))`。
- ratio 与统计输出精度统一为 3 位小数：
  - CSV ratio（如 `10.000%`）
  - stats JSON / stats CSV 中数值
  - HTML 报告中的统计与阈值百分比展示

### 文档与测试

- `README.md` 补充 3 位小数与绝对值均值说明。
- `tests/test_compare_path_summary.py` 增加 ratio 精度与绝对值均值断言。

---

## [0.4.3] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 统一 timing path 抽取与 PT report_timing 生成的实现路径：移除旧版脚本，实现推荐库 `lib` 的多进程解析，并为 PT TCL 生成脚本增加多进程模式。

### 变更

- 移除 `scripts/parse_timing_rpt.py` 及其在 README 中的旧脚本说明，统一推荐使用 `python -m lib` 进行 timing 报告解析。
- `lib/cli.py` 增加 `-j/--jobs` 参数，支持基于 path 维度的多进程解析（path 数量较少时自动回退为单进程）。
- `scripts/gen_pt_report_timing.py` 增加 `-j/--jobs` 参数，支持按 path 并行生成 `report_timing` 命令（path 数较少时回退为单进程）。

### 文档

- `README.md`：
  - 删除旧版 `scripts/parse_timing_rpt.py` 章节。
  - 标注 `python -m lib` 与 `gen_pt_report_timing.py` 的多进程能力与新参数说明。

---

## [0.4.1] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 调整 `compare_path_summary` 的 ratio 输出格式：从小数改为百分比字符串（带 `%`），使结果更直观。

### 变更

- `arrival_time_ratio` / `required_time_ratio` / `slack_ratio` 统一改为百分比输出（例如 `10.000%`）。
- 统计/相关性/图表流程已兼容百分比输入解析。
- 阈值默认值从 `0.1` 调整为 `10`（即 10%），与百分比单位保持一致。
- HTML 报告中的统计与阈值字段改为带 `%` 展示，和 CSV ratio 单位一致。

### 文档与测试

- `README.md` 同步更新公式、阈值说明与示例参数。
- `tests/test_compare_path_summary.py` 增加百分比格式断言并更新阈值测试。

---

## [0.4.0] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 增强 `scripts/compare_path_summary.py`：在原有对比 CSV 基础上，新增统计输出、图表输出与 HTML 汇总报告，便于快速评估 golden/test 差异分布与相关性。

### 新增

- **统计输出**：
  - 默认输出 `compare_stats.json`（结构化）。
  - 可选输出 `compare_stats.csv`（扁平化，需指定 `--stats-csv`）。
  - 覆盖指标：`arrival_time_ratio` / `required_time_ratio` / `slack_ratio` 的 `count/min/max/mean/median/std`、`p90/p95/p99`、阈值超限统计（`abs(ratio) > threshold`）与相关性（Pearson）。
- **图表输出（matplotlib）**：
  - 直方图 3 张（每个 ratio 一张）
  - 箱线图 1 张（3 个 ratio 同图）
  - 散点图 3 张（两两组合）
  - 默认输出目录：`<output_dir>/charts`，支持 `--charts-dir` 自定义。
- **HTML 汇总报告**：
  - 输出 `compare_report.html`
  - 包含输入文件信息、样本数、统计摘要、阈值摘要、相关性摘要与图表展示。
- **CLI 参数扩展**：
  - `--threshold`、`--bins`、`--charts-dir`
  - `--no-charts`、`--no-html`
  - `--stats-json`、`--stats-csv`
- **依赖策略**：
  - 若缺少 `matplotlib`，脚本尝试自动安装后继续执行；安装失败时跳过图表生成并保留统计输出。

### 测试

- 新增 `tests/test_compare_path_summary.py`，覆盖：
  - 统计计算（分位数、阈值、相关性）
  - 默认/自定义 CLI 参数组合
  - 统计文件输出、HTML 报告生成
  - 图表文件存在性检查（matplotlib 可用时执行）

### 文档

- `README.md` 更新 `compare_path_summary.py` 的新参数、输出说明与命令示例。

---

## [0.3.1] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 增强 PT report_timing 转换脚本输出控制：支持统一 report 文件变量并将每条 report_timing 结果重定向到该文件。

### 新增

- `scripts/gen_pt_report_timing.py` 在生成 tcl 开头增加：
  - `set output_file "report_file.rpt"`
  - `sh rm -rf ${output_file}`
  - `sh touch ${output_file}`
- 每条 `report_timing` 命令末尾自动追加 `>> ${output_file}`（包括无 through 参数场景）。

### 测试

- `tests/test_gen_pt_report_timing.py` 新增重定向相关断言：
  - 有 through 参数时追加 `>> ${output_file}`
  - 无 through 参数时也追加 `>> ${output_file}`

---

## [0.3.0] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 为 timing path 的 input/output pin 新增统一属性 `trigger_edge`，并用于 PT `report_timing` 参数生成，保证 across format_1 / format_2 / pt 的触发沿语义一致。

### 新增

- **format1 / pt**：从 `Path` 最后一列 `r/f` 提取 `trigger_edge`。
- **format2**：根据 `Time` 与 `Description` 之间分隔符提取 `trigger_edge`（` / ` -> `r`，` \ ` -> `f`）。
- **转换脚本**：`scripts/gen_pt_report_timing.py` 改为优先按 `trigger_edge` 映射 through 参数（`r -> -rise_through`，`f -> -fall_through`）。

### 兼容性

- 若 `launch_path.csv` 未包含 `trigger_edge`（旧版本 CSV），`gen_pt_report_timing.py` 自动回退到旧规则（按 pin 名启发式判断 rise/fall），兼容历史流程。

### 测试

- `tests/test_format1_parser.py`：新增 `trigger_edge` 提取断言。
- `tests/test_format2_parser.py`：新增 `trigger_edge`（`/`、`\`）提取断言。
- 新增 `tests/test_pt_parser.py`：PT 解析与 `trigger_edge` 提取。
- 新增 `tests/test_gen_pt_report_timing.py`：脚本通过参数映射测试。

### 文档

- `README.md`：更新三种格式的 `trigger_edge` 规则、测试命令与 report_timing 参数生成规则。

---

## [0.2.2] - 2026-03-10

### 更新时间

- **日期**：2026-03-10

### 更新原因与概要

- 修复 format1(APR) 在部分报告中 **capture 段 clock 行不带 rise/fall edge**（如 `clock CORE_CLK`）导致 capture path 无法识别的问题。

### 修复

- **format1**：clock 段起始识别支持 `clock <clock_name>`（不带 edge）与 `clock <clock_name> (rise|fall edge)` 两种形式，并避免将 `clock network delay (propagated)` 等描述行误识别为段起点。

### 新增

- **测试**：`tests/test_format1_parser.py` 新增 capture clock 无 edge 的用例。

### 文档

- **README**：更新 format1 兼容说明，说明 edge 可选与 `clock network delay` 过滤规则。

---

## [0.2.1] - 2026-03-09

### 更新时间

- **日期**：2026-03-09

### 更新原因与概要

- 修复 format1(APR) 解析中 **clock 行匹配硬编码为 CPU_CLK** 导致在其它时钟名报告中无法识别 launch/capture 段的问题。
- 兼容更多触发沿文本（包括 `falling rising edge-triggered`），提升模板化适配能力。
- 增加 format1 测试用例，避免回归；同时移除仓库中误跟踪的 `input/` 大文件，确保不上传测试数据。

### 修复

- **format1**：点表段起始识别从 `clock CPU_CLK (rise edge)` 改为 `clock <clock_name> (rise|fall edge)`，不再依赖固定时钟名。
- **format1**：`clocked by` 时钟名提取更宽松（支持下划线等字符）。

### 新增

- **测试**：新增 `tests/test_format1_parser.py`，覆盖：
  - 任意 clock 名（非 CPU_CLK）
  - `(rise edge)` / `(fall edge)` 两类 clock 行
  - Startpoint/Endpoint 中 `falling rising edge-triggered` 文案

### 仓库与发布

- 从仓库索引中移除 `input/place_REG2REG.rpt`（仅删除远端跟踪，保留本地文件），避免上传测试输入数据；`input/` 仍由 `.gitignore` 排除。
- **README**：补充 format1 的兼容说明与识别规则。

---

## [0.2.0] - 2025-03-09

### 更新时间

- **日期**：2025-03-09

### 更新原因与概要

- 修复 format2 解析在部分报告下 **x-coord、y-coord 误入 Derate 列** 的问题（当 Derate 与坐标连写时）。
- 修复 format2 **point 名称被列宽截断**（前/后缺字）的问题。
- 完善 format2 **port** 类型属性与 **y-coord** 解析，并补充测试与文档。

### 新增

- **format2**：当 Derate 列内容含 `{x,y}`（如 `0.900,0.900{219.156,772.737}`）时，自动拆成 Derate 与 x-coord、y-coord，避免坐标写入 Derate 列。
- **format2 port**：支持属性 **Trans**，以及通过 ` / ` 或 ` \ ` 正确解析 Description（与 pin 一致）。
- **测试**：`tests/test_format2_parser.py` 增加 Derate+xy 拆分、多类型 point 名称、y-coord 与截断相关用例。

### 修复

- **format2 pin/port**：Description 改为按行内最后一个 ` / ` 或 ` \ ` 取整段，不再依赖列起始位置，避免 point 名前/后被截断。
- **format2**：合并 x-coord 与 y-coord 列内容后再解析坐标，修复 y-coord 在部分报告中为空的问题。
- **format2**：各类型保留 **Type** 列，便于结果检查与测试。

### 文档

- **README**：更新 format2 解析规则（port 含 Trans、x-coord、y-coord）；补充 Derate 与坐标连写、point 截断的兼容说明；增加测试目录与运行方式；补充“测试”小节。

### 依赖与兼容

- Python 3.6+
- 无新增第三方依赖；与既有 format1/pt 行为兼容。

---

## [0.1.0] - 历史版本

- lib 架构：TimeParser 抽象类 + format1/format2/pt 实现 + CLI（`python -m lib`）。
- format2 按 Type 分派解析，使用 split/列切片，支持 clock/port/net/pin/constraint/required/arrival/slack。
- path_summary 输出与 compare_path_summary 对比脚本。
