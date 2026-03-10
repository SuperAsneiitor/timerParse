# Release Notes

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
