---
name: timerextract-skill-router
description: Top-level router for timerExtract skills. Use to choose the right skill for parser/report code changes, STA concept questions, validation execution, LVF/non-LVF regression, and test result reporting workflows.
---

# timerExtract Skill Router

## 第一性原理

- **目标**：以最小试错成本，把用户问题转换为“正确 Skill + 可验证动作”。
- **对象**：代码、语义、验证、汇报四类任务。
- **约束**：任何代码改动都必须回到可验证结果（non-LVF/LVF、时间戳产物、可复盘）。
- **闭环**：任务分类 -> Skill 路由 -> 执行 -> 验证 -> 结构化汇报。

## Quick Start

1. 先判断任务主类型：`实现` / `解释` / `验证` / `复盘`。
2. 选择 1 个主 Skill；跨域任务再加 1~2 个辅助 Skill。
3. 输出前检查是否满足“验证闭环”。

## 3-Step Decision Tree

**Step 1：用户是否要求改代码？**

- 是 -> 进入 Step 2
- 否 -> 进入 Step 3

**Step 2：改动是否涉及 parser/gen/extract/compare？**

- 是 -> 主 Skill：`python-coding-standards`  
  辅助：`timing-validation-flow`（必选），`test-validation-rules`（汇报时）
- 否 -> 主 Skill：`python-coding-standards`（按常规工程改动执行）

**Step 3：用户主要是在问“概念”、还是“验证/复盘”？**

- 概念解释（STA/PT、launch/capture、arrival/required/slack）  
  -> `timing-path-basics`
- 验证执行（格式回归、compare、LVF/non-LVF）  
  -> `timing-validation-flow` + `test-validation-rules`
- 复盘风险（假通过、语义回归、迭代易错）  
  -> `iteration-pitfalls`

## Routing Rules

- **改 Python 代码/重构/评审风格**  
  -> `python-coding-standards`
- **解释 STA / PT 报告字段 / launch-capture-slack**  
  -> `timing-path-basics`
- **跑三格式全链路验证（format1/format2/pt）**  
  -> `timing-validation-flow`
- **约束测试输出目录、回归规则、结果模板**  
  -> `test-validation-rules`
- **复盘迭代易错点、排查“看似通过但语义回归”**  
  -> `iteration-pitfalls`

## Composed Workflows

### Parser / Extract 改动

1. `python-coding-standards`（先做实现规范）
2. `timing-validation-flow`（执行 non-LVF + 必要时 LVF）
3. `test-validation-rules`（按规范汇报结果）

### 生成报告结构异常（如 clock/port/data_path）

1. `timing-path-basics`（先判定结构语义是否正确）
2. `python-coding-standards`（修改生成器/解析器）
3. `timing-validation-flow` + `test-validation-rules`（回归验证并汇报）

### 用户只问概念不要求改代码

1. `timing-path-basics`
2. 仅输出解释，不触发实现与验证流程

## Fast Decision Table

| 用户意图关键词 | 首选 Skill | 备选 Skill |
|---|---|---|
| parser / extract / refactor / coding style | `python-coding-standards` | `timing-validation-flow` |
| STA / PT / launch / capture / slack / arrival / required | `timing-path-basics` | `test-validation-rules` |
| validate / regression / compare / format1 format2 pt | `timing-validation-flow` | `test-validation-rules` |
| test_results / timestamp / PASS FAIL / report template | `test-validation-rules` | `timing-validation-flow` |
| LVF / --lvf / extract-chaos / long data_path | `timing-validation-flow` | `test-validation-rules` |
| pitfall / regression risk / 假通过 / 卡住复盘 | `iteration-pitfalls` | `timerextract-skill-router` |

## Checklist

- [ ] 已识别任务主类型
- [ ] 已选择匹配 Skill（必要时组合 2~3 个）
- [ ] 若涉及代码改动，已包含验证步骤
- [ ] 若涉及验证，已按模板汇报路径与结果
- [ ] 若涉及回归风险，已执行 `iteration-pitfalls` 过筛
