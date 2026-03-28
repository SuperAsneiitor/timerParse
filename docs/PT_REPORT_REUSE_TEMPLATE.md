# Timing 报告改造复用模板（基于 PT 实战）

本模板用于把 PT 报告对齐经验复用到 `format1` / `format2`。  
目标：先定义“结构顺序”，再定义“指标规则”，最后定义“命名规范”。

---

## 1. 结构顺序模板（必须先定）

### 1.1 Header

- Startpoint
- Endpoint
- Last common pin（如果该格式有“公共点”概念）
- Path Group
- Path Type

### 1.2 Launch Path

1) clock 信息（`clock ... (rise/fall edge)` + `clock source latency`）  
2) port 信息（可选）  
3) launch clock path：多组 `input_pin -> output_pin -> net`  
4) data path：多组 `input_pin -> output_pin -> net`  
5) endpoint + `data arrival time`

### 1.3 Capture Path

1) clock 信息（`clock ...` + `clock source latency`）  
2) port 信息（可选）  
3) 多组 `input_pin -> output_pin -> net`（包含 Last common pin）  
4) endpoint  
5) 约束项（例如 reconvergence/uncertainty/library setup）  
6) `data required time`

### 1.4 Summary Block（分隔符位置固定）

- 分隔符
- `data arrival time`
- `data required time`
- 分隔符
- `statistical adjustment`
- `slack (MET|VIOLATED)`

---

## 2. 指标语义与规则模板

### 2.1 累加规则

- `Path = cumsum(Incr)`（按段独立累加：launch 一套、capture 一套）

### 2.2 字段展示规则

- `Derate`：pin 行固定 4 位小数（示例 `1.1000`）
- `Mean` / `Sensit`：非 net 行建议 4 位小数，net 行可留空
- `Incr` 追加后缀：`&`（例：`0.0453 &`）
- `Path` 追加边沿标记：`r/f`（例：`0.3528 r`、`0.1882 f`）
- `slack >= 0` -> `MET`；`slack < 0` -> `VIOLATED`

#### 2.2.1 PT 数值精度与特殊行

- **clock 行（launch/capture 第一行）**：  
  - 只展示 `Mean/Incr/Path`，不展示 `Trans/Sensit`（保持与实际 PT 报告一致）；  
  - `Mean/Incr/Path` 保留 4 位小数。  
- **clock source latency 行**：第二行文案统一为 `clock source latency`，其数值同样按 4 位小数输出。  
- **端口行 `dft_clk (in)`**：在 `Trans, Mean, Sensit, Incr, Path` 上均应有数值，便于验证端口一侧 clock 路径的解析。  
- **统一精度**：在生成与解析（**lib/parser**，含 extract 与 extract-chaos）端保持一致：  
  - `Fanout` 为整数；  
  - `Cap, Trans, Derate, Mean, Sensit, Incr, Path` 统一 4 位小数。

### 2.3 约束项位置规则

- `clock reconvergence pessimism` 和 `clock uncertainty` 放在 capture path 的后段，**紧邻 data required time 前**，不要出现在中段路径点之间。

---

## 3. 命名规范模板（stdcell 风格）

### 3.1 端口命名

- port 名不要带层次 `/`（例如 `in_port_1`）

### 3.2 pin 区分

- input pin：常见 `I/A1/A2/CK/D`
- output pin：常见 `Q/Z/ZN`

### 3.3 point 结构

- input/output pin：`<inst>/<pin> (<cell_type>)`
- net：`<net_name> (net)`

---

## 4. YAML/生成器落地清单

### 4.1 Schema 组织（base + override）

1. 公共规则放到 `config/gen_report/base.yaml`：  
   - `variables`  
   - `row_type_profiles`  
   - `point_generator` 通用模板  
2. 各格式只保留差异覆盖（`format1.yaml` / `format2.yaml` / `pt.yaml`）：  
   - `table.columns` 差异列  
   - `structure.launch/capture` 差异结构  
   - `summary_policy` 差异 summary 行

### 4.2 PT 关键落地

1. 在 `point_generator` 中补齐专用 row type：  
   - `clock_net_delay`（文案用 `clock source latency`）  
   - `clock_reconv`、`clock_uncertainty`、`library_setup`  
   - `input_pin`、`output_pin`、`net`、`endpoint`、`common_pin`
2. `structure.launch` / `structure.capture` 改成“分段 + 多组”结构，不用单段扁平写法。  
3. 渲染层做字段后处理：  
   - `Incr` -> `xxxx &`  
   - `Path` -> `xxxx r/f`
4. summary 区块用固定流程输出，确保分隔符位置稳定（`summary_policy` 控制 `statistical adjustment`）。

---

## 5. 自检清单（每次改完都要跑）

- [ ] 分隔符位置是否与模板一致（header 后、launch/capture 边界、summary 内）。
- [ ] launch/capture 是否都包含“多组 input/output/net”。
- [ ] Last common pin 是否在标题出现，且在 capture path point 中真实出现。
- [ ] `clock source latency` 文案是否正确（不再是 `clock network delay (ideal)`）。
- [ ] `Incr` 是否带 `&`，`Path` 是否带 `r/f`。
- [ ] slack 标签是否与数值符号一致。

