---
name: iteration-pitfalls
description: Capture common timerExtract iteration mistakes and prevention checks. Use during feature iteration, parser/report refactor, LVF/non-LVF validation, or when diagnosing why a change "looks correct" but regresses behavior.
---

# Iteration Pitfalls

## 第一性原理

- **目标**：优先拦截“看似通过、实则语义回归”的错误。
- **方法**：从症状反推根因，建立硬性 guardrails。
- **闭环**：发现风险 -> 定位根因 -> 加断言/加流程 -> 防止再次发生。

## Quick Start

在每次迭代末尾，用这份清单做一次快速过筛：

1. 结构语义是否对齐（不仅是行数对齐）
2. 单测是否覆盖“长路径 + 关键字段”
3. 是否完成 non-LVF + LVF 双轨回归
4. README / Skill 是否与实际流程同步

## High-Risk Pitfalls

### 1) 语义对齐错误（高风险）

- **Startpoint 与 launch 数据起点不一致**  
  现象：`data_path_point_count` 变 0，launch 全落入 `launch_clock`。
- **LVF 合成结构简化过度**  
  现象：launch/capture 缺 `clock source latency` 或 `propagated port`，报告结构“看起来不真”。
- **只看 CSV 行数一致**  
  现象：`extract` 与 `extract-chaos` 都“通过”，但路径边界语义已漂移。

### 2) 测试假通过（高风险）

- 只断言 `summary_rows == 100`，未断言 `data_path_point_count` 下限。
- 未断言 LVF 关键列（如 `TransMean/IncrMean/PathMean`）存在。
- 只跑局部单测，不跑完整回归链路。

### 3) 流程漏项（中高风险）

- 改完 parser/gen 后没跑 `run_validation_flow.py`。
- 涉及 LVF 改动但没跑 `run_lvf_100_validation.py`。
- 脚本/行为改了但 Skill 与 README 未同步，后续执行口径错位。

### 4) 工具/环境误用（中风险）

- PowerShell 里使用 `&&` 造成命令失败。
- 文本文件误用 notebook 编辑工具。
- 输出目录未加时间戳，导致多轮结果互相覆盖。

## Guardrails (Must Pass)

- [ ] `Startpoint` 与 launch 首个 output pin 对齐
- [ ] `data_path_point_count` 设有最小阈值断言
- [ ] LVF 关键列存在性已断言
- [ ] non-LVF 回归：`python scripts/run_validation_flow.py --jobs 4`
- [ ] LVF 回归（相关改动时）：`python scripts/run_lvf_100_validation.py`
- [ ] 输出目录使用时间戳并可追溯
- [ ] README 与 Skill 已同步更新

## Symptom -> Root Cause

| 症状 | 常见根因 | 优先检查点 |
|---|---|---|
| `data_path` 行数异常偏小/为 0 | Startpoint 不匹配、边界行位置错 | `splitLaunchByCommonPin` 输入与报告点名 |
| capture/launch 只有一条 clock 行 | 合成器遗漏 `clock source latency/port` | 合成模板结构与 `format1.yaml` 对齐 |
| 行数都一致但结果不可信 | 只做数量校验未做语义校验 | `path_type`、点序列、边界字段 |
| 一轮通过下一轮复现失败 | 输出目录被覆盖或口径漂移 | 时间戳目录、README/Skill 是否同步 |

## Reporting Template

```markdown
迭代风险扫描结论：
- 结构语义：PASS/FAIL
- 测试覆盖：PASS/FAIL
- 双轨回归：PASS/FAIL
- 文档同步：PASS/FAIL

发现问题：
- [风险级别] 症状 -> 根因 -> 修复动作

防回归动作：
- 新增/加强断言：
- 新增/更新脚本：
- 文档/Skill 同步项：
```
