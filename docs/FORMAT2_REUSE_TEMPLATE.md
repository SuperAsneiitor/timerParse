# Format2 报告改造复用模板（基于 PT 实战）

本模板用于把 PT 报告改造经验完整复用到 `format2`。  
目标：固定结构层次、字段列位、边沿符号和分隔规则，避免“看起来接近但无法抽取”的问题。

---

## 1. 结构顺序模板（必须先定）

### 1.1 Header

- Scenario
- Path Start
- Path End
- Common Pin（必须是真实公共点，不能是时钟名）
- Group Name
- Analysis Type

### 1.2 Launch Path

1) `Type=clock`  
2）port信息
3) 多组 `Type=pin -> Type=pin -> Type=net`  
4) `Type=arrival`（launch 终止行）

### 1.3 Launch 与 Capture 的边界

- launch 与 capture 之间使用**空行**分隔
- 边界处不使用 `-=-=-` 分隔符

### 1.4 Capture Path

1) `Type=clock`
2）port信息  
3) 多组 `Type=pin -> Type=pin -> Type=net`  
4) `Type=constraint`  
5) `Type=required`（必须紧跟 constraint）  
 分隔符 （使用-=-=-=格式）
6) `Type=required`  
7) `Type=arrival`  
 分隔符 （使用-=-=-=格式）
8) `Type=slack`

### 1.5 Path 组间切分

- `slack` 后不加 `-=-=-`  
- 使用空行 + 下一组 Header 开始新 path

---

## 2. 指标语义与列位规则模板

### 2.1 累加规则

- `Time = cumsum(Delay)`  
- launch 和 capture 视为两段，各自维护累计上下文

### 2.2 summary 数值规则

- `required` 行：`Time` 写 capture 累计值  
- `arrival` 行：`Time` 写 launch 累计值的负数  
- `slack` 行：`Time` 写 `required + arrival`

### 2.3 列位规则（强约束）

- `data required time`、`data arrival time`、`slack` 的数值必须在 `Time` 列
- `Description` 列只承载文本（如 `data required time`）
- 不允许把 summary 数值挤到 `Description` 列

---

## 3. 边沿符号规则模板（Format2 专项）

### 3.1 适用行

- 仅 `Type=pin` 行使用边沿符号  
- `clock/net/constraint/required/arrival/slack` 行不使用边沿符号

### 3.2 符号规则

- 上升沿使用 `/`
- 下降沿使用 `\`
- 符号和 point 文本必须单空格连接：`/ <point>`、`\ <point>`

---

## 4. 坐标格式规则模板（Format2 专项）

### 4.1 包裹规则

- `x-coord` 前缀带 `{  `
- `y-coord` 后缀带 `}`

### 4.2 目标显示示例

- `x-coord`: `{  317.863`
- `y-coord`: `829.474}`

说明：左右花括号在两列中拆分显示，不在同一列闭合。

---

## 5. 命名规范模板

### 5.1 Common Pin 规则

- Common Pin 必须来自真实公共点
- 不允许使用 clock 名替代 Common Pin

### 5.2 pin 成对规则

- 相邻 input/output pin：
  - point 主体实例保持一致（同一个 `Uxx`）
  - stdCell 名保持一致
  - 仅 pin 名变化（如 `A2 -> Q`、`CK -> ZN`）

### 5.3 Type 字段规则

- pin 类型统一显示为 `pin`
- 不显示 `input_pin` / `output_pin` 标签

---

## 6. YAML/生成器落地清单

1. `row_templates` / `capture_row_templates` 使用组语义：`group: [input_pin, output_pin, net]`。  
2. `Type` 字段映射到 `display_type`，确保 pin 统一显示为 `pin`。  
3. 渲染阶段为 pin 行注入 `description_text`，并按边沿写 `/` 或 `\`。  
4. 渲染阶段对 `x-coord/y-coord` 做 `{ x` 与 `y}` 包裹后处理。  
5. capture summary 结构固定：`constraint -> required -> arrival -> slack`。  
6. 路径切分固定：launch/capture 空行分隔，slack 后空行起下一组 path。

---

## 7. 自检清单（每次改完都要跑）

- [ ] Common Pin 是否为真实点（非时钟名）。
- [ ] launch/capture 是否都满足多组 `pin -> pin -> net`。
- [ ] launch 与 capture 是否使用空行分隔。
- [ ] `constraint` 后是否紧跟 `required`。
- [ ] `slack` 后是否不再输出 `-=-=-` 分隔线。
- [ ] pin 行是否同时存在 `/` 与 `\`。
- [ ] pin 行符号是否是单空格格式（`/ point`、`\ point`）。
- [ ] 坐标是否按 `{ x` / `y}` 形式输出。
- [ ] required/arrival/slack 数值是否在 `Time` 列。

