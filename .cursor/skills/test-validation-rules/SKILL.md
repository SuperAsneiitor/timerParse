---
name: test-validation-rules
description: Enforce timerExtract test/validation conventions: timestamped test_results outputs, mandatory post-change validation, LVF+non-LVF regression requirements, and consistent PASS/FAIL reporting format.
---

# Test & Validation Rules

## 第一性原理

- **目标**：让每次验证都“可比较、可追溯、可复现”。
- **核心资产**：时间戳目录 + 统一口径（PASS/FAIL + 关键行数）。
- **底线**：没有可追溯产物的验证，等同于未验证。

## Quick Start

每次改动后，至少执行：

```bash
python scripts/run_validation_flow.py --jobs 4
```

涉及 LVF 或 `--lvf` 抽取时，再执行：

```bash
python scripts/run_lvf_100_validation.py
```

## Use When

- 运行测试、验证脚本、回归流程。
- 修改报告生成、解析、抽取、compare 相关代码。
- 汇报测试结果给用户时。

## Output Rules

- 所有验证产物必须放到 `test_results/` 下的时间戳目录：
  - `test_results/<prefix>_YYYYMMDD_HHMMSS/`
- 禁止写入固定名称目录或无时间戳目录（例如 `test_results/tmp_*`、固定文件名 `.rpt` 作为长期产物）。

## Post-Change Validation Rules

1. **Non-LVF 必跑**：`python scripts/run_validation_flow.py --jobs 4`
2. **LVF 相关改动必跑**：`python scripts/run_lvf_100_validation.py`
3. 任一步失败必须立即修复并重跑，直到全部通过。
4. 完整回归标准：Non-LVF 100 paths + LVF 100 paths（长 `data_path`）。

## Completion Checklist

- [ ] 三格式报告已生成
- [ ] 五行 CSV 齐全（launch/capture/launch_clock/data_path/summary）
- [ ] compare 输出与 stats JSON 齐全
- [ ]（LVF 场景）`extract` 与 `extract-chaos` 行数一致

## Reporting Template

```markdown
验证目录：
- <timestamped path>

执行项：
- run_validation_flow: PASS/FAIL
- run_lvf_100_validation: PASS/FAIL (如执行)

关键行数：
- format1: ...
- format2: ...
- pt: ...

异常：
- 无 / <详细异常与修复动作>
```
