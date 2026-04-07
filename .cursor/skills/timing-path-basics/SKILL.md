---
name: timing-path-basics
description: Explain STA/PT timing-path concepts: launch path, capture path, data arrival time, data required time, slack, setup/hold, CRPR, and uncertainty. Use for timing report interpretation, structure checks, and path-level root-cause analysis.
---

# Timing Path Basics

## 第一性原理

- **目标**：先确定 timing 语义，再讨论实现细节。
- **第一问题**：这条路径是否满足 `required - arrival = slack` 的一致性。
- **分解方式**：`header -> launch -> capture -> summary`，逐段验证结构与指标语义。

## Quick Start

当用户问 STA 路径或 PT 报告字段时，按以下顺序回答：

1. 先标出路径结构：`header -> launch -> capture -> summary`。
2. 再解释关键指标：`Incr/Path`（或 `Delay/Time`）、`arrival/required/slack`。
3. 最后给出判断：是否 MET、差异来自 data 侧还是 clock 侧。

## Use When

- 解释 `launch path` / `capture path` 基本概念。
- 解释 PT 风格报告字段含义。
- 校验报告结构是否符合 STA 语义。
- 对比两份同一路径的 timing 报告并定位差异来源。

## Core Concepts

### Path Structure

- **Header**：`Startpoint`、`Endpoint`、`Last common pin`、`Path Group`、`Path Type`。
- **Launch**：`clock`/`clock source latency`/可选 `port` + data 点列，结尾 `data arrival time`。
- **Capture**：clock 段 + data 点列，尾部常见 `clock reconvergence pessimism`、`clock uncertainty`、`library setup/hold`，再到 `data required time`。
- **Summary**：`data arrival time`、`data required time`、`slack (MET|VIOLATED)`。

### Metric Semantics

- `Incr`/`Delay`：单行增量延迟。
- `Path`/`Time`：段内累计值（通常为增量累加）。
- `data arrival time`：数据实际到达检查点时间。
- `data required time`：约束允许的最迟/最早到达时间。
- `slack`：通常按 `required - arrival`；`>=0` 为 `MET`，`<0` 为 `VIOLATED`。

## Analysis Workflow

1. **结构对齐**：检查 header、launch、capture、summary 是否完整。
2. **段级检查**：确认 launch/capture 中 clock 段与 data 段边界清晰。
3. **数值一致性**：检查累计列是否满足累加关系，`slack` 标签与符号是否一致。
4. **根因归类**：
   - `launch_clock_delay` 差异大、`data_path_delay`接近：偏时钟建模差异。
   - `data_path_delay` 差异大：偏组合逻辑/RC/derate 差异。
   - `clock_uncertainty` 或 `CRPR` 差异大：偏时钟保守量处理差异。

## Output Template

按以下固定结构回复：

```markdown
结论：结构对齐 / 不对齐

差异明细：
- Header:
- Launch:
- Capture:
- Summary:

可能根因：
- ...

修复建议：
- 配置侧（YAML / row_templates）：
- 渲染侧（report_gen / parser）：
```

## Quick Checklist

- [ ] `Last common pin` 同时出现在 header 与点表
- [ ] launch/capture 都有 clock 段与 data 段
- [ ] `arrival/required/slack` 顺序与语义一致
- [ ] `MET/VIOLATED` 与 slack 符号一致

