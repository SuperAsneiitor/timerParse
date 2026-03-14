# YAML Schema 迁移指南（旧 -> 新）

本项目已切换为 **base + override** 配置模式，支持 `extends` 与语义化分段配置。

## 1. 关键映射

- `path_vars` -> `variables`
- `path_table.column_order` -> `table.column_order`
- `path_table.columns` -> `table.columns`
- `path_table.row_templates` -> `structure.launch`
- `path_table.capture_row_templates` -> `structure.capture`
- `path_table.cumulative_rules` -> `table.cumulative_rules`
- `when_type`（仍可用）+ 新增 `profiles`（由 `row_type_profiles` 展开）
- 新增 `summary_policy`（用于 summary 固定行规则，如 PT `statistical adjustment`）

## 2. 新增基础模板

- 新文件：`config/gen_report/base.yaml`
- 用法：在格式文件头部添加 `extends: base.yaml`
- 覆盖策略：子文件字段覆盖基础模板同名字段；字典按键深度合并

## 3. 最小迁移示例

旧：

```yaml
path_vars:
  clock: { type: fixed, value: "clk" }
path_table:
  cumulative_rules: { Path: Incr }
  row_templates:
    - { type: clock, count: 1 }
```

新：

```yaml
extends: base.yaml
variables:
  clock: { type: fixed, value: "clk" }
table:
  cumulative_rules: { Path: Incr }
structure:
  launch:
    - { type: clock, count: 1 }
```

## 4. 不兼容说明

- 旧配置不再作为默认推荐方式（内部会尽量兼容 legacy 字段）。
- 新功能（`profiles`、`summary_policy`、`extends`）仅在新 schema 下完整生效。
