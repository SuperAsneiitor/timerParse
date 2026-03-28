# timerExtract：`lib/` 架构说明

本文档描述当前仓库 **`lib/`** 内模块的职责划分与数据流，便于开发与阅读代码。

---

## 1. 第一性原理：三层分工

| 层 | 职责 | 典型路径 |
|----|------|----------|
| **解析** | 报告文本 → 结构化行（内存 dict/list），**不写文件** | `lib/parser/` |
| **抽取编排** | 多 path 合并、launch 按 startpoint 拆分、**写 CSV** | `lib/extract.py`、`lib/parser/parallel_extract.py` |
| **下游工具** | gen-pt / compare / 报告生成 | `lib/gen_pt_report_timing.py`、`lib/compare*`、`lib/report_gen/` |

命令行入口保持**薄**：`lib/cli.py`（及 `lib/__main__.py`）只做参数解析与调用上述模块。

---

## 2. `lib/parser/`（唯一完整解析实现）

- **`time_parser_base.py`**：`TimeParser` 抽象基类、`ParseOutput`、`splitLaunchByCommonPin`、定宽列解析、`writeCsv`。
- **`format1_parser.py` / `format2_parser.py` / `pt_parser.py`**：三种版式的具体解析（`scanPathBlocks`、`parseOnePath`）。
- **`layout_config.py` / `layout_runtime.py`**：加载 `config/parse_layouts/*.yaml`，供按类型 + token 的辅助解析逻辑使用。
- **`engine.py`**：`create_timing_report_parser()`、`detect_report_format()`；**`TimingParserV2`**：基于 `lib/parser/layouts/*.yaml` 的轻量布局解析（`parse_text` → `ParseResult`），与完整 CSV 流水线可并存。
- **`parallel_extract.py`**：多进程队列抽取（`runExtractParallel` / `runExtractChaos`）；与 `extract` 共用同一套 `TimeParser`，仅调度模型不同。
- **`layouts/*.yaml`**：布局引擎用配置；与 `config/parse_layouts/` 可配合使用。

**已移除**：历史上的 `lib/parsers/` 包；**不再提供**根目录 `lib/format1_parser.py` 等薄转发，请从 `lib.parser` 导入。

---

## 3. `lib/extract.py`（主抽取路径）

- 调用 **`create_timing_report_parser`**，单进程或 `multiprocessing.Pool` 解析整份报告。
- 输出与下游约定一致的 5 个 CSV：`launch_path.csv`、`capture_path.csv`、`path_summary.csv`、`launch_clock_path.csv`、`data_path.csv`。
- **`SEMANTIC_POINT_ATTRS`**：与格式无关的语义列并集，用于 CSV 表头。

---

## 4. `lib/parser/parallel_extract.py`（高吞吐抽取）

- **同一套解析器**：Worker 内 **`create_timing_report_parser` + `parseOnePath`**，与 `extract` 一致。
- **差异仅在进程模型**：1 个分割器进程读文件、切块入队；N 个 Worker 从队列取块解析；主进程聚合写 CSV。
- **列与 `path_summary` schema**：通过 **`TimeParser.summary_columns` / `attrs_order`** 与 `extract` 对齐（模块内 `_csv_layout`）。

---

## 5. 其他 `lib/` 顶层模块

| 模块 | 说明 |
|------|------|
| `report_gen/` | YAML → 合成 `.rpt` |
| `compare/`、`compare_path_summary.py` | path_summary 对比与 HTML 报告；`path_detail_html.py` 生成单 path 详情（逐点对比表头 sticky + 限高滚动） |
| `gen_pt_report_timing.py` | `launch_path.csv` → `report_timing` TCL |
| `log_util.py` | 日志等级 |
| `__init__.py` | `createParser` / `detectReportFormat` 等兼容导出 |

---

## 6. 配置目录（仓库根）

| 路径 | 说明 |
|------|------|
| `config/gen_report/` | 报告生成 YAML |
| `config/parse_layouts/` | 解析辅助布局（`layout_runtime` 加载） |

---

## 7. 相关文档

- [extract_parallel.md](extract_parallel.md) — 多进程队列流水线细节与用法  
- [FORMAT_VALIDATION.md](FORMAT_VALIDATION.md) — 三格式校验约定  
- [PARSE_LAYOUTS.md](PARSE_LAYOUTS.md) — parse_layouts 配置说明  
