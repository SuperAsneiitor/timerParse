# 轻量 parse_layouts 配置化解析

本项目新增了一套“轻量配置化解析”机制，用于降低 Timing 报告解析对固定列宽/正则的强依赖。

核心思路：

- **先按行类型（point_type / row_kind）分类**（如 clock/net/pin/required/arrival/slack）
- **再按配置的 token 位置或行尾数值顺序抽取字段**（0-based）
- 抽取结果与原 parser 的 fixed-width 结果合并（渐进式接入，保留回退）

对应配置目录：`config/parse_layouts/`

- `format1.yaml`
- `format2.yaml`
- `pt.yaml`

---

## 1. 术语

- **token**：一行按空白 `split()` 切分后的片段。
- **0-based**：第一个 token 的索引为 0。
- **row_kind_numeric**：按“行尾倒取 N 个数值”的顺序，映射到字段列表。
- **type_layouts**：按行类型（clock/constraint/required...）定义更具体的抽取策略。

---

## 2. 最常用配置：row_kind_numeric（推荐）

适用场景：

- `Incr/Path`、`Delay/Time`、`Mean/Sensit/...` 等数值列通常稳定出现在行尾
- 但列宽可能漂移、对齐可能变化

示例（format1）：

```yaml
format: format1

row_kind_numeric:
  clock: [Incr, Path]
  net: [Incr, Path]
  pin: [Incr, Path]
```

含义：

- 从该行中提取所有数值 token（正负号/小数都算）
- 取行尾最后 2 个数值，依次赋值给 `Incr`、`Path`

---

## 3. type_classify：先分类再抽取

适用场景：format2。

format2 的首 token 通常为 Type（如 `clock`/`pin`/`net`/`constraint`），并可能包含关键字行（arrival/required/slack）。

示例片段：

```yaml
type_classify:
  - id: pin-from-type
    priority: 100
    emit: pin
    when:
      token_eq: { index: 0, value: pin }

  - id: required-by-text
    priority: 50
    emit: required
    when:
      contains: "data required time"
```

规则说明：

- `priority` 越大越先匹配
- `when` 支持：
  - `token_eq`：指定 token 位置等于某字符串
  - `contains`：整行包含指定子串（不区分大小写）
  - `regex`：整行匹配正则

---

## 4. type_layouts：按类型定义字段抽取

目前项目中用于 format2 的 clock/constraint/required/arrival/slack/port。

常用策略：

- `tail_numeric: [Delay, Time]`：从行尾倒取数值
- `point_from: after_last_numeric`：把最后一个数值 token 后面的文本作为 point/description

示例：

```yaml
type_layouts:
  clock:
    point_from: after_last_numeric
    tail_numeric: [Delay, Time]
```

---

## 5. 新增属性怎么做（最短路径）

1. 确认该属性在某类行上出现（例如 clock 行新增 `Skew`）
2. 若属性稳定出现在行尾：优先扩展 `row_kind_numeric` 或 `type_layouts.<type>.tail_numeric`
3. 若属性是固定 token 位置：扩展 `type_layouts`（后续可按需要支持 `idx`/`idx_range`）
4. 执行完整验证：

```bash
python -m unittest discover -s tests -v
python scripts/run_validation_flow.py --jobs 4
```

---

## 6. 代码入口（供开发者）

- 配置加载：`lib/parser_V2/layout_config.py`（`config/parse_layouts/*.yaml`）
- 运行时：`lib/parser_V2/layout_runtime.py`
- 接入点（完整解析与定宽逻辑）：
  - `lib/parser_V2/format1_parser.py`（`_parseNumericColumns` 等）
  - `lib/parser_V2/pt_parser.py`
  - `lib/parser_V2/format2_parser.py`（clock/constraint/required/arrival/slack/port 等）

