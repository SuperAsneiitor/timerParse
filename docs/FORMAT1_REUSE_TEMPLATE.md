# Format1 报告改造复用模板（基于 PT 实战）

本模板用于把 PT 报告改造经验完整复用到 `format1`。  
目标：先固定“结构顺序”，再固定“指标规则”，最后固定“命名与校验规则”。

---

## 1. 结构顺序模板（必须先定）

### 1.1 Header

- Startpoint
- Endpoint
- Common Pin（必须是真实公共点，不能是时钟名）
- Scenario
- Path Group
- Path Type

### 1.2 Launch Path

1) clock 信息：`clock ... (rise edge)`  
2) launch/data 路径点：多组 `input_pin -> output_pin -> net`  
3) 终止行：`data arrival time`

### 1.3 Launch 与 Capture 的边界

- Launch 与 Capture 之间使用**一个空行**分隔  
- 该边界处不放分隔符（不放长横线）

### 1.4 Capture Path

1) clock 信息：`clock ... (rise edge)`  
2) capture 路径点：多组 `input_pin -> output_pin -> net`  
3) 约束项（顺序固定，不能打乱）：
   - `path check period`
   - `clock reconvergence pessimism`
   - `clock uncertainty`
   - `library setup time`
4) summary 收敛区（固定顺序）：
   - 分隔线
   - `data required time`（带数值）
   - `data arrival time`（带负值）
   - 分隔线
   - `slack (MET|VIOLATED)`（带数值）
   - 分隔线

---

## 2. 指标语义与计算规则模板

### 2.1 累加规则

- `Path = cumsum(Incr)`  
- 按段独立累加：launch 一套，capture 一套

### 2.2 summary 规则

- `data required time` 取 capture 段累计值  
- `data arrival time` 取 launch 段累计值的相反数（负值）  
- `slack = required - arrival(abs)`（实现上与上面两值一致即可）

### 2.3 字段展示规则

- `Path` 后缀追加 `r/f`（与 PT 同风格）  
  - 示例：`0.352 r`、`0.188 f`
- `Incr` 保持数值格式，不强制 `&`

### 2.4 约束项位置规则

- `path check period`、`clock reconvergence pessimism`、`clock uncertainty`、`library setup time`  
  必须在 capture path 后段、`data required time` 之前集中出现，不允许插入到中段路径点里。

---

## 3. 命名规范模板

### 3.1 Common Pin 规则

- Common Pin 必须来自真实路径公共点
- 不允许使用 clock 名替代 Common Pin

### 3.2 pin 组规则

- 相邻 input/output pin：
  - point 主体实例必须一致（同一个 `Uxx`）
  - stdCell 名必须一致
  - 仅 pin 名变化（如 `CK -> Z`、`A2 -> Q`）

### 3.3 net 规则

- net 行显示为 `... (net)` 形式
- 每组 net 对应前一对 input/output pin

---

## 4. YAML/生成器落地清单

1. `row_templates` / `capture_row_templates` 必须采用“分段 + 多组”结构，不使用扁平随机堆叠。  
2. launch/capture 的重复点必须由组语义生成：`group: [input_pin, output_pin, net]`。  
3. 在 capture 中补齐约束 row type：  
   - `path_check_period`
   - `clock_reconv`
   - `clock_uncertainty`
   - `library_setup`
4. 渲染阶段为 `Path` 增加 `r/f` 后缀。  
5. summary 阶段固定输出：
   - `data required time`
   - `data arrival time`
   - `slack`
   并保证分隔线位置稳定。

---

## 5. 自检清单（每次改完都要跑）

- [ ] Header 中 Common Pin 是否为真实点（非时钟名）。
- [ ] launch/capture 是否都满足多组 `input -> output -> net` 循环。
- [ ] launch 与 capture 之间是否为“单空行分隔”。
- [ ] capture 是否包含 `path check period`、`clock reconvergence pessimism`、`clock uncertainty`、`library setup time`。
- [ ] `data required time`、`data arrival time`、`slack` 是否都有数值且顺序正确。
- [ ] `Path` 是否带 `r/f` 后缀，且边沿变化逻辑连续。
- [ ] 分隔线位置是否固定（required 前、slack 前、slack 后）。

