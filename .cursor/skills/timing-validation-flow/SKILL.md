---
name: timing-validation-flow
description: Run timerExtract end-to-end validation for format1/format2/pt and LVF/non-LVF regressions. Use when running generation->extract->compare, checking extract vs extract-chaos parity, or validating 100-path long data_path scenarios.
---

# Timing Validation Flow

## 第一性原理

- **目标**：证明“改动没有破坏功能语义”，而不是只证明“脚本能跑完”。
- **最小完备证据**：`generate -> extract -> compare` +（LVF 场景）`extract vs extract-chaos`。
- **核心不变量**：三格式产物齐全、五行 CSV 齐全、compare 可追溯、目录带时间戳。

## Quick Start

仓库根目录执行：

```bash
python scripts/run_validation_flow.py --jobs 4
```

当改动涉及 format1 LVF、`--lvf` 抽取或 launch/data 分界时，再额外执行：

```bash
python scripts/run_lvf_100_validation.py
```

## Use When

- 用户要求三格式端到端验证（`format1/format2/pt`）。
- 改动了报告生成、解析、抽取、compare 任一环节。
- 需要验证 LVF 与非 LVF 的一致性与回归稳定性。

## Standard Flow

1. 生成 3 份报告：`format1`、`format2`、`pt`。
2. 分别抽取 CSV。
3. 用 `pt/path_summary.csv` 作为 golden，对比 `format1` 和 `format2`。
4. 若涉及 LVF，执行 `run_lvf_100_validation.py` 做 `extract` vs `extract-chaos` 行数一致性验证。

## Full Regression Requirement

完整回归必须覆盖两条线，且都为 100 path：

- **Non-LVF**：`python scripts/run_validation_flow.py --jobs 4`
  - 来自 `config/gen_report/base.yaml` 的 `num_paths: 100`。
- **LVF**：`python scripts/run_lvf_100_validation.py`
  - 合成 100 条 format1 LVF 长 `data_path`，并校验 `extract` 与 `extract-chaos`。

## Required Output Layout

输出必须在时间戳目录，例如：

- `test_results/validation_flow_YYYYMMDD_HHMMSS/`
- 子目录：`reports/`、`extract_format1/`、`extract_format2/`、`extract_pt/`、`compare/`

## Checklist

- [ ] `reports/` 下存在三份 `.rpt`
- [ ] 每个 extract 目录包含五行 CSV：`launch_path.csv`、`capture_path.csv`、`launch_clock_path.csv`、`data_path.csv`、`path_summary.csv`
- [ ] `compare/` 下存在 `pt_vs_format1.csv`、`pt_vs_format2.csv` 及 stats JSON
- [ ] 涉及 LVF 时，`run_lvf_100_validation.py` 结果为 OK
- [ ] 结果可复盘（命令、目录、关键行数已记录）

## Report Template

向用户汇报时使用：

```markdown
验证目录：
- <timestamped base path>

行数摘要：
- format1: launch/capture/summary=...
- format2: launch/capture/summary=...
- pt: launch/capture/summary=...

对比结果：
- pt_vs_format1: <path>
- pt_vs_format2: <path>
- stats: <paths>

LVF 结果（如执行）：
- extract vs extract-chaos: 一致 / 不一致

异常：
- 无 / <具体异常>
```
