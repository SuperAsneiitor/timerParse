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
# 与 lib extract 保持同一输出结构（5 个 CSV）
python scripts/run_extract_chaos.py path/to/report.rpt -o output_parser_chaos --format auto -j 4

# 或在代码中调用
from lib.parser_chaos import runExtractChaos
runExtractChaos(
    report_path,
    output_dir,
    format_key="format2",  # format1 / format2 / pt / apr
    num_workers=4,
)
```

参数与现有 `extract` 子命令类似：

- `-o`, `--output-dir`：输出目录；
- `--format`：`auto` / `format1` / `format2` / `pt` / `apr`（其中 `apr` 与 `format1` 为同一格式，入口会统一映射为 `format1`）；
- `-j`, `--jobs`：解析器 Worker 数量（默认 3，推荐与本机 CPU 核数接近但略小，例如 4/8）。

脚本会自动：

1. 调用 `detectFormatFromReport`（或使用 `--format` 显式指定）识别格式；
2. 启动分割器 + N 个 Worker，并在所有 Worker 结束后聚合结果；
3. 将解析结果写出为与 `python -m lib extract` **完全相同 schema** 的 5 个 CSV 文件。

## 目录结构

```
lib/parser_chaos/
  __init__.py      # 导出 runExtractChaos、detectFormatFromReport、ParseOutput
  constants.py     # 格式键（FORMAT1/format2/pt）、哨兵、列名常量
  models.py        # ParseOutput 数据类
  utils.py         # normalizePin、cleanMetricFloat、extractColumnPositions、parseFixedWidthAttrs、fillUncertainty、sumDelayInRows
  splitter.py      # 分割器进程入口与各格式切分逻辑
  parser_format1.py # Format1/APR 单条 path 解析
  parser_format2.py # Format2 单条 path 解析（Type/Fanout/Cap/Delay/Time/Description 全量支持）
  parser_pt.py     # PT 单条 path 解析
  worker.py        # 解析器 Worker 进程入口
  aggregator.py    # splitLaunchByCommonPin、aggregateResults
  run.py           # 流水线编排、collectResults、writeOutputCsv、detectFormatFromReport
```

## 输出文件

与现有 `python -m lib extract` 一致：会在输出目录生成 5 个 CSV：

- `launch_path.csv`
- `capture_path.csv`
- `path_summary.csv`
- `launch_clock_path.csv`
- `data_path.csv`

其中：

- `launch_path.csv` 额外包含 `path_type` 列，值为 `launch_clock` / `data_path`，规则与 `lib/parsers` 中 `splitLaunchByCommonPin` 一致（startpoint 所在行为 data_path，其前为 launch_clock）；
- `path_summary.csv` 列与主解析栈对齐：  
  `path_id,startpoint,endpoint,arrival_time,required_time,slack,uncertainty,launch_clock_point_count,data_path_point_count,capture_point_count,launch_clock_delay,data_path_delay`；
- `uncertainty` 列为每条 path 的 **clock uncertainty 数值**，由 path 文本中的 `clock uncertainty` 行提取。

这意味着：对同一输入报告，`lib/extract` 与 `parser_chaos` 的 `path_summary.csv` 可以直接用 `lib compare` 对比。

针对 **PT 报告**，parser_chaos 与主解析栈在数值上也保持同一约定：

- `Fanout` 解析为整数；
- `Cap, Trans, Derate, Mean, Sensit, Incr, Path` 统一按 4 位小数写入 CSV；
- `Incr` 列会去掉原始 PT 报告中的 `&` 符号，仅保留数值部分。

针对 **Format1 (APR) 报告**，parser_chaos 与主解析栈在数值解析上也做了类似的“智能映射”：

- 不再单纯依赖列名起始位置做固定宽度切片来决定 Fanout/Cap/Trans/Incr/Path 的归属；  
- 会先按行内容判断行为 clock / net / pin，再基于「行类型 + 数值 token 顺序」映射数值列：  
  - clock 行只映射 `Incr, Path`；  
  - net 行映射 `Fanout, Cap, Incr, Path`；  
  - pin 行映射 `Cap, Trans, Incr, Path`。  
- 这样可以更稳健地处理列间距略有变化或外部 APR 报告中的对齐差异，同时保证与 `lib extract` 输出一致。

## 依赖

与主项目相同：Python 3.9+，无额外第三方依赖（仅标准库 + 项目已有 PyYAML/matplotlib）。

---

## 与验证 Flow 的配合

推荐使用 `scripts/run_validation_flow.py` 作为**统一验证入口**：

```bash
python scripts/run_validation_flow.py --jobs 4
```

该脚本会：

1. 通过 `gen-report` 生成 format1/format2/pt 三类报告；
2. 使用主解析栈（`lib extract`）抽取三类报告；
3. 以 PT 的 `path_summary` 作为 golden，对 format1/format2 的 `path_summary` 做对比；
4. 将所有输出写入 `test_results/validation_flow_YYYYMMDD_HHMMSS/` 下的子目录。

在开发/修改 `lib/parser_chaos` 的解析逻辑之后，建议：

1. 先对生成的 format1/format2/pt 报告分别运行一次 `scripts/run_extract_chaos.py`，确认 5 个 CSV 的行数与主解析栈一致；
2. 再运行 `scripts/run_validation_flow.py --jobs 4`，以 PT 为 golden 检查 path 级差异是否在预期范围内。
