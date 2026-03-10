# Release Notes

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
