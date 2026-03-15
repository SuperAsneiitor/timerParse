# 会话迁移说明（跨机续用）

本文档用于在新机器上快速恢复项目与会话上下文，便于继续开发或使用 Cursor 助手。

---

## 1. 项目与目标

- **仓库**：timerParse（GitHub: SuperAsneiitor/timerParse）
- **核心目标**：解析/生成三种 Timing 报告格式（format1、format2、pt），用 YAML 模板统一控制生成，以 PT 结果为 golden 校验 format1/format2 抽取结果。
- **两套解析实现**：
  - **lib/parsers + lib/extract**：主流程；主进程 scanPathBlocks 后 Pool.map 或单进程 parseReport。
  - **lib/parser_chaos**：独立实现；1 个分割器进程 + N 个解析器进程 + 队列，分割与解析分离、任务动态分配。

---

## 2. 格式约定（近期统一）

- **format1 与 apr**：视为同一种格式，代码内统一为 **FORMAT1**（`constants.FORMAT1 = "format1"`）。CLI 仍支持 `--format apr`，入口处会规范成 `format1`。parser_chaos 中已删除 FORMAT_APR/FORMAT_FORMAT1，仅保留 FORMAT1。

---

## 3. 目录与关键文件

| 路径 | 说明 |
|------|------|
| **lib/parser_chaos/** | 独立解析流水线：splitter / worker / aggregator / run，不引用 lib.parsers |
| **lib/parsers/** | 原有解析器：time_parser_base、format1_parser、format2_parser、pt_parser |
| **lib/extract.py** | 原有 extract 入口，调用 parsers |
| **lib/report_gen/** | 报告生成（YAML → .rpt） |
| **config/gen_report/** | base.yaml、format1.yaml、format2.yaml、pt.yaml |
| **scripts/run_extract_chaos.py** | parser_chaos 命令行入口 |
| **scripts/run_validation_flow.py** | 一键验证 flow（生成 3 格式 → 抽取 → PT 作 golden 对比） |
| **.cursor/skills/** | timing-path-basics、timing-validation-flow、python-coding-standards |

---

## 4. 常用命令（新机恢复后）

```bash
# 依赖
pip install -r requirements.txt

# 原有解析（extract）
python -m lib extract path/to/report.rpt -o output_lib --format auto -j 4

# parser_chaos 解析（分割器 + N 个 Worker）
python scripts/run_extract_chaos.py path/to/report.rpt -o output_parser_chaos --format auto -j 3

# 生成报告
python -m lib gen-report config/gen_report/format1.yaml --seed 101 -o output/gen_format1.rpt

# 一键验证
python scripts/run_validation_flow.py --jobs 4
```

---

## 5. 分支与远程

- **parser_chaos 相关分支**：带时间戳，例如 `feature/parser-chaos-20260314_164829`。
- **远程**：`origin` → `https://github.com/SuperAsneiitor/timerParse.git`。
- 在新机克隆后，可拉取对应分支继续开发或合并。

---

## 6. 近期变更摘要

- 新增 **lib/parser_chaos**：分割器进程 + 解析器 Worker 进程 + 队列；与 lib.parsers 完全独立。
- **格式统一**：FORMAT_FORMAT1 与 FORMAT_APR 统一为 FORMAT1；入口处将 `apr` 规范为 `format1`。
- **文档**：README 增加 parser_chaos 小节；docs/parser_chaos.md 描述架构与用法；本文件为会话迁移说明。

---

## 7. 文档索引

- [README.md](../README.md)：项目总览与统一入口用法。
- [docs/parser_chaos.md](parser_chaos.md)：parser_chaos 架构、用法、与 extract 的差异。
- [docs/FORMAT_VALIDATION.md](FORMAT_VALIDATION.md)：三格式结构对比与验证说明。
- [.cursor/skills/python-coding-standards/](../.cursor/skills/python-coding-standards/)：Python 编码规范（驼峰、中文注释、单一职责等）。

保存本文件并在新机打开项目后，可将上述要点提供给 Cursor 以恢复上下文。
