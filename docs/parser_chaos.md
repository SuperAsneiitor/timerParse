# parser_chaos 流水线解析

## 概述

`lib/parser_chaos` 是一套与 `lib/parsers` **完全独立**的 Timing 报告解析实现，采用「1 个报告分割器进程 + N 个报告解析器进程 + 队列」的架构：分割器只负责读报告并切分 path 块放入任务队列，解析器进程从队列取块并解析，主进程收集结果后聚合并写出 CSV。

## 架构

- **分割器进程（1 个）**：读取报告文件，按格式（format1/format2/pt）将报告切分为多条 Timing Path 文本块，将 `(path_id, path_text)` 放入 `task_queue`，完成后放入结束哨兵。
- **解析器 Worker 进程（N 个）**：从 `task_queue` 取任务；若为哨兵则退出并向结果队列放入哨兵；否则根据格式调用对应解析函数，将 `(path_id, meta, launch_rows, capture_rows)` 放入 `result_queue`。
- **主进程**：启动分割器与 N 个 Worker，从 `result_queue` 收集结果直至收到 N 个结束哨兵；按 `path_id` 排序后调用聚合逻辑（按 startpoint 将 launch 拆为 launch_clock / data_path），写出 5 个 CSV。

## 与现有 extract 的差异

| 项目       | lib.extract + lib.parsers     | lib.parser_chaos                    |
|------------|-------------------------------|-------------------------------------|
| 分割所在   | 主进程一次性 scanPathBlocks   | 独立分割器进程，边读边放入队列       |
| 解析所在   | 主进程或 Pool.map 的 worker   | 独立 N 个解析器进程                 |
| 任务分配   | 全量 block 列表静态分片       | 队列动态分配，空闲 Worker 取下一块  |
| 代码依赖   | lib.parsers 各格式解析器      | parser_chaos 内自包含，不引用 parsers |

## 用法

```bash
# 使用脚本（推荐）
python scripts/run_extract_chaos.py path/to/report.rpt -o output_parser_chaos --format auto -j 3

# 或在代码中调用
from lib.parser_chaos import runExtractChaos
runExtractChaos(report_path, output_dir, format_key="format1", num_workers=3)
```

参数与现有 `extract` 子命令类似：`-o` 输出目录，`--format` 为 `auto`/`format1`/`format2`/`pt`/`apr`，`-j` 为解析器 Worker 数量（默认 3）。

## 目录结构

```
lib/parser_chaos/
  __init__.py      # 导出 runExtractChaos、detectFormatFromReport、ParseOutput
  constants.py     # 格式键、哨兵、列名常量
  models.py        # ParseOutput 数据类
  utils.py         # normalizePin、cleanMetricFloat、extractColumnPositions、parseFixedWidthAttrs、sumDelayInRows
  splitter.py      # 分割器进程入口与各格式切分逻辑
  parser_format1.py # Format1/APR 单条 path 解析
  parser_format2.py # Format2 单条 path 解析（当前为 meta 最小实现）
  parser_pt.py     # PT 单条 path 解析
  worker.py        # 解析器 Worker 进程入口
  aggregator.py    # splitLaunchByCommonPin、aggregateResults
  run.py           # 流水线编排、collectResults、writeOutputCsv、detectFormatFromReport
```

## 输出文件

与现有 extract 一致：`launch_path.csv`、`capture_path.csv`、`path_summary.csv`、`launch_clock_path.csv`、`data_path.csv`。

## 依赖

与主项目相同：Python 3.9+，无额外第三方依赖（仅标准库 + 项目已有 PyYAML/matplotlib）。
