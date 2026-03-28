# 会话迁移说明（跨机续用）

本文档用于在新机器上快速恢复项目与会话上下文，便于继续开发或使用 Cursor 助手。

---

## 1. 项目与目标

- **仓库**：timerExtract / timerParse（以你远程名为准）
- **核心目标**：解析/生成三种 Timing 报告格式（format1、format2、pt），用 YAML 模板统一控制生成，以 PT 结果为 golden 校验 format1/format2 抽取结果。
- **解析与抽取**：
  - **lib/parser**：唯一完整解析实现（`TimeParser` 子类）。
  - **lib/extract**：主进程路径；`Pool` 或单进程解析后写 CSV。
  - **lib/parser/parallel_extract.py**：**同一解析器**；1 分割器 + N Worker + 队列，仅调度模型不同。

---

## 2. 格式约定（近期统一）

- **format1 与 apr**：视为同一种格式，代码内统一为 **FORMAT1**（`parallel_extract.FORMAT1 = "format1"`）。CLI 仍支持 `--format apr`，入口处会规范成 `format1`。

---

## 3. 目录与关键文件

| 路径 | 说明 |
|------|------|
| **lib/parser/** | 解析器与基类：format1/2/pt、`create_timing_report_parser`、`TimingParserV2` |
| **lib/parser/parallel_extract.py** | 高吞吐抽取：分割器 / Worker / 聚合 / 写 CSV；与 extract 共用 TimeParser |
| **lib/extract.py** | extract 入口，调用 lib.parser |
| **lib/report_gen/** | 报告生成（YAML → .rpt） |
| **config/gen_report/** | base.yaml、format1.yaml、format2.yaml、pt.yaml |
| **scripts/run_extract_chaos.py** | extract-chaos 脚本入口（调用 `parallel_extract.runExtractChaos`） |
| **scripts/run_validation_flow.py** | 一键验证 flow（生成 3 格式 → 抽取 → PT 作 golden 对比，`path_summary` 包含 `uncertainty` 等列） |
| **.cursor/skills/** | timing-path-basics、timing-validation-flow、python-coding-standards |

---

## 4. 常用命令（新机恢复后）

```bash
# 依赖
pip install -r requirements.txt

# 原有解析（extract）
python -m lib extract path/to/report.rpt -o output_lib --format auto -j 4

# extract-chaos / parallel_extract（分割器 + N 个 Worker）
python scripts/run_extract_chaos.py path/to/report.rpt -o output_parser_chaos --format auto -j 3

# 生成报告
python -m lib gen-report config/gen_report/format1.yaml --seed 101 -o output/gen_format1.rpt

# 一键验证
python scripts/run_validation_flow.py --jobs 4
```

---

## 5. 分支与远程

- **extract-chaos / 多进程抽取相关分支**：带时间戳，例如 `feature/parser-chaos-20260314_164829`。
- **远程**：`origin` → `https://github.com/SuperAsneiitor/timerParse.git`。
- 在新机克隆后，可拉取对应分支继续开发或合并。

---

## 6. 近期变更摘要

- **lib/parsers 已移除**：解析代码统一在 **lib/parser**。
- **parallel_extract（extract-chaos）** 与 **extract** 共用 **`lib.parser`**；已移除独立包 `lib/parser_chaos/`。
- **格式统一**：`apr` 与 `format1` 同义；入口处规范为 `format1`。
- **文档**：见 [ARCHITECTURE.md](ARCHITECTURE.md)、[extract_parallel.md](extract_parallel.md)。

---

## 7. 文档索引

- [README.md](../README.md)：项目总览与统一入口用法。
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)：`lib/` 模块划分与数据流。
- [docs/extract_parallel.md](extract_parallel.md)：extract-chaos 流水线。
- [docs/FORMAT_VALIDATION.md](FORMAT_VALIDATION.md)：三格式结构对比与验证说明。
- [.cursor/skills/python-coding-standards/](../.cursor/skills/python-coding-standards/)：Python 编码规范（驼峰、中文注释、单一职责等）。

保存本文件并在新机打开项目后，可将上述要点提供给 Cursor 以恢复上下文。
