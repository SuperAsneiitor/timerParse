---
name: python-coding-standards
description: Apply timerExtract Python standards (layering, Chinese docstrings/comments, camelCase functions, single responsibility, ~100-line function limit). Use when editing parser, report generator, extract/compare flow, or doing Python code review/refactor.
---

# Python Coding Standards

## 第一性原理

- **目标**：降低复杂度与回归概率，让代码“可读、可改、可验证”。
- **对象**：分层边界、命名一致性、函数复杂度、注释可解释性。
- **判据**：职责单一、边界清晰、测试可覆盖、改动可回滚定位。

## Quick Start

修改 Python 代码时，默认执行以下规则：

1. 先确认分层：生成(`lib/report_gen`) / 解析(`lib/parser`) / 抽取与对比(`lib/extract`, `lib/compare`) / CLI(`lib/cli.py`)。
2. 函数命名用 `camelCase`，变量命名用 `snake_case`。
3. 模块、类、公开函数写中文 docstring。
4. 单函数控制在约 100 行；超长立即拆分。
5. 改完先跑最小相关测试，再跑完整验证流。

## Use When

- 编写或重构本仓库 Python 代码。
- 新增/修改报告生成器、解析器、抽取或对比逻辑。
- 代码评审需要统一风格与可维护性标准。

## Layering Rules

- **生成层**：只根据 YAML 生成 `.rpt`，不读报告、不写 CSV。
- **解析层**：只做文本解析与字段归一化，不做文件输出。
- **抽取/对比层**：负责 I/O（CSV 写入、compare 输出）。
- **CLI/脚本层**：保持薄入口，只做参数和流程编排。

## Naming Rules

- **函数/方法**：`camelCase`（例如 `parseOnePath`、`splitLaunchByCommonPin`）。
- **类**：`PascalCase`。
- **变量/参数/常量**：`snake_case`。
- **私有成员**：前缀 `_`，其余规则不变。

## Comment & Docstring Rules

- 模块顶部必须有中文 docstring，说明职责和位置。
- 公开函数必须写中文 docstring（参数、返回、关键流程）。
- 正则、单位换算、多分支等复杂逻辑必须有中文注释解释意图。

## Function Design Rules

- 单一职责：一个函数只解决一个明确问题。
- 长度上限：建议不超过约 100 行。
- 参数过多时，使用 dataclass/TypedDict 聚合。

## Self Checklist

- [ ] 分层没有越界（parser 不写文件、CLI 不塞业务）
- [ ] 新增函数为 `camelCase`
- [ ] 变量/常量为 `snake_case`
- [ ] 关键逻辑有中文说明
- [ ] 已执行相关测试与验证流
