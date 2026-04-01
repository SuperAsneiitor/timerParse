# extract-chaos（`lib.parser.parallel_extract`）流水线

## 概述

`lib/parser/parallel_extract.py` 提供 **「1 个分割器进程 + N 个 Worker 进程 + 队列」** 的 Timing 报告抽取流水线。

**解析实现与 `lake extract` 完全相同**：Worker 内使用 **`lib.parser.engine.create_timing_report_parser`**，对每块 path 调用 **`TimeParser.parseOnePath`**。与主路径的差异**仅在于进程与任务调度模型**，不维护第二套解析代码。

## 架构

- **分割器进程（1 个）**：读报告文件，按版式（format1 / format2 / pt）切分为多条 path 文本块，将 `(path_id, path_text)` 放入 `task_queue`，最后向队列放入与 Worker 数量相同的结束哨兵。
- **Worker 进程（N 个）**：从 `task_queue` 取任务；若为哨兵则向结果队列放入哨兵并退出；否则解析后将 `(path_id, meta, launch_rows, capture_rows)` 放入 `result_queue`。
- **主进程**：启动分割器与 N 个 Worker；从 `result_queue` 收集直至收到 N 个结束哨兵；按 `path_id` 排序后聚合（`TimeParser.splitLaunchByCommonPin`），写出与 **`extract` 一致 schema** 的 CSV。

## 与 `extract` 的差异

| 项目 | `extract`（`lib/extract.py`） | `parallel_extract` |
|------|------------------------------|---------------------|
| 分割 | 主进程 `scanPathBlocks` 得到全量列表 | 独立分割器进程边读边入队 |
| 解析 | 主进程或 `Pool.map` | N 个独立 Worker 从队列取块 |
| 任务分配 | 静态列表分片 | 队列动态分配 |
| 解析器 | `lib.parser` | **同一** `lib.parser` |

## 用法

```bash
# 推荐：统一 CLI（与 extract 参数风格一致）
python -m lib extract-chaos path/to/report.rpt -o output_parser_chaos -f auto -j 4

# 或在代码中调用
from lib.parser.parallel_extract import runExtractParallel
runExtractParallel(
    report_path,
    output_dir,
    format_key="format2",  # format1 / format2 / pt / apr（apr 入口会规范为 format1）
    num_workers=4,
)
```

兼容旧名：`runExtractChaos`、`detectFormatFromReport` 与 `parallel_extract` 中同名符号等价。

- **格式**：`auto` 时由 **`detect_report_format`**（与 `lib.parser` 一致）识别。
- **`-j`**：Worker 数量（CLI `extract-chaos` 默认 3）；大文件可适当增大，注意内存与句柄。
- **分片**：`-p N`、`-m` 与 `extract` 语义相同。
- **LVF**：`--lvf` 与 `extract --lvf` 相同，要求抽取结果中出现 LVF 语义字段，否则报错。

**`scripts/run_extract_chaos.py`** 内部调用 `lib.parser.parallel_extract.runExtractChaos`，与上述 CLI 行为一致。

## 模块位置

实现集中在单文件 **`lib/parser/parallel_extract.py`**（分割、Worker、聚合、写 CSV）。

## 输出文件

与 `python -m lib extract` 相同，默认 5 个 CSV：

- `launch_path.csv`（含 `path_type`：`launch_clock` / `data_path`）
- `capture_path.csv`
- `path_summary.csv`（列与 **`TimeParser.summary_columns`** 一致）
- `launch_clock_path.csv`
- `data_path.csv`

对同一输入、同一 `-f`，`extract` 与 `extract-chaos` 的 schema 应对齐；数值行数应一致（调度顺序不影响逐 path 结果）。

## 依赖

Python 3.10+ 推荐；无额外强制第三方依赖（`gen-report`/`compare` 另见主 README）。

## 与验证 Flow

可使用 **`scripts/run_validation_flow.py`** 做端到端生成与对比；若改了解析逻辑，建议同时跑 **`extract`** 与 **`extract-chaos`** 对比输出行数与关键列。
