# Timing 报告三种格式对比与验证

本文档对比 **format1**、**format2**、**pt** 三种真实报告的结构，说明生成器输出与真实报告在格式上的一致性及属性累加关系。

---

## 1. 格式结构对比

| 项目 | format1 (APR) | format2 | pt (PrimeTime) |
|------|----------------|--------|-----------------|
| **Title 形式** | `  Startpoint: ...`<br>`  Endpoint: ...`<br>`  Common Pin: ...`<br>`  Scenario: ...`<br>`  Path Group: ...`<br>`  Path Type: ...` | `  Scenario                :  value`<br>`  Path Start              :  value`<br>`  Path End                :  value`<br>`  Common Pin         :  value`<br>`  Group Name          :  value`<br>`  Analysis Type         :  value` | `  Startpoint: ...`（可多行）<br>`  Endpoint: ...`（可多行）<br>`  Path Group: ...`<br>`  Path Type: ...` |
| **表头列** | Point, Fanout, Cap, Trans, Location, Incr, Path | Type, Fanout, Cap, D-Trans, Trans, Derate, x-coord, y-coord, D-Delay, Delay, Time, Description | Point, Fanout, Cap, Trans, Derate, Mean, Sensit, Incr, Path |
| **首列** | Point（点名一整列） | Type（clock/pin/net/…） | Point（点名一整列） |
| **累加关系** | **Path = cumsum(Incr)** | **Time = cumsum(Delay)** | **Path = cumsum(Incr)** |
| **trigger** | Path 列末位 r/f | Description 前 `/` 或 `\` 表示 r/f | Path 列末位 r/f |

---

## 2. 属性累加关系（生成器已实现）

- **format1 / pt**：每行有 `Incr`（本段增量），`Path` 为从段首到当前行的 **Incr 累加和**。生成器在 `table` 中默认 `cumulative_rules: { Path: Incr }`，按段（launch / capture）分别累加后填入 Path。
- **format2**：每行有 `Delay`（本段延迟），`Time` 为从段首到当前行的 **Delay 累加和**。生成器默认 `cumulative_rules: { Time: Delay }`，按段累加后填入 Time。

YAML 中可通过 `table.cumulative_rules` 覆盖，例如：

```yaml
table:
  cumulative_rules: { Time: Delay }   # format2
  # 或
  cumulative_rules: { Path: Incr }   # format1 / pt
```

---

## 3. PT 指标语义字典（统一语义层）

| 指标 | 层级 | 典型值类型 | 精度建议 | 适用 row_type | 是否参与累加 |
|------|------|------------|----------|---------------|--------------|
| `Fanout` | row-level | int | 0 位 | net | 否 |
| `Cap` | row-level | float | 3~4 位 | net / pin（视格式） | 否 |
| `Trans` | row-level | float | 3~4 位 | pin / input_pin / output_pin | 否 |
| `Derate` | row-level | float/string | 固定 4 位（PT） | pin / input_pin / output_pin | 否 |
| `Mean` | row-level | float | 4 位 | clock/pin/约束类（net 可空） | 否 |
| `Sensit` | row-level | float | 4 位 | clock/pin/约束类（net 可空） | 否 |
| `Incr` | row-level | float | 2~4 位 | clock/net/pin/约束类 | 是（驱动 `Path`） |
| `Path` | segment-level | float(+r/f) | 2 位显示 | 与 `Incr` 同步的行 | 由 `Incr` 推导 |
| `Delay` | row-level | float | 3 位 | format2 的 delay 行 | 是（驱动 `Time`） |
| `Time` | segment-level | float | 3 位 | format2 的 time 行 | 由 `Delay` 推导 |
| `arrival_time` | path-level | float | 3 位 | summary | 否 |
| `required_time` | path-level | float | 3 位 | summary | 否 |
| `slack` | path-level | float | 3 位 | summary | 否 |

> 说明：三种格式显示差异可保留，但语义输出统一到同一字典（列可为空），便于后续对比与 golden 校验。

---
## 4. 生成器与真实报告格式差异说明

| 格式 | 生成器支持 | 与真实报告差异 |
|------|------------|----------------|
| **format2** | 完整支持：Title（Scenario, Path Start, Path End, Common Pin, Group Name, Analysis Type）、表头与列顺序、Type/Fanout/Cap/Delay/Time/Description、累加 Time=cumsum(Delay)、分隔线。 | 可选：x-coord/y-coord 为 `{ x y }` 或纯数字由配置决定；Description 中 `/`、`\` 与 trigger 的对应关系与真实报告一致。 |
| **format1** | 支持 Title（Startpoint, Endpoint, Common Pin, Scenario, Path Group, Path Type）、表头 Point + Fanout/Cap/Trans/Location/Incr/Path、Path=cumsum(Incr)。 | 需在 YAML 中配置 column_order 为 format1 列顺序；Point 列由 Description/point 提供；真实报告中 “Point” 为整列点名，生成器用统一列配置输出。 |
| **pt** | 支持 Title（Startpoint, Endpoint, Path Group, Path Type）、表头 Point + Fanout/Cap/Trans/Derate/Incr/Path、Path=cumsum(Incr)。 | Startpoint/Endpoint 多行样式可选；列顺序与 format1 类似但无 Location、有 Derate。 |

---

## 5. 验证方式

1. **固定脚本入口**：执行 `python scripts/run_validation_flow.py`。
2. **目录约束**：结果输出到 `test_results/validation_flow_YYYYMMDD_HHMMSS/`，包含 `reports/`、`extract_*`、`compare/`。
3. **golden 对比**：`pt` 作为 golden，自动输出 `pt_vs_format1.csv`、`pt_vs_format2.csv` 及统计 JSON。

测试结果统一存放于 `test_results/`，文件名或子目录带时间戳（见 test_results/README.md）。

---

## 6. 最近规则更新（2026-03）

- `launch_path.csv` 新增 `path_type` 列：`launch_clock` / `data_path`。
- `path_summary.csv` 的 `launch_clock_delay`、`data_path_delay` 在写出时做浮点清理，避免超长小数尾巴。
- PT 解析分段规则增强：当 `Startpoint` 为实例名（如 `u_logic/Uu73z4_reg`）时，能正确匹配到对应 output pin（如 `/Q`）并切分 `data_path`。
- PT 生成对齐 raw 风格：`clock network delay (ideal)`、capture 段保留关键约束行、`input_pin/output_pin` 的 `Derate` 输出为 4 位小数（例如 `1.1000`）。
- 新模板 schema 支持 `extends` + `base.yaml` + format override，`row_type_profiles` 可收敛 `when_type` 配置。
- 新增固定验证脚本 `scripts/run_validation_flow.py`，默认强制时间戳目录输出。
- PT / Format1 报告的点表解析从「依赖列名起始位置的定宽切分」升级为「按行类型 + 数值 token 顺序补齐关键数值列」，其中 **Incr/Path 等累加相关列只依赖行内数值 token 顺序恢复，不再受列起始位置影响，Cap/Trans/Fanout 等仍结合定宽解析**；**extract** 与 **extract-chaos** 共用 **lib/parser**，数值行为一致。
- Format2 解析补强：支持 net 行 `Cap` 后单位 **`xd` / `xf`**（含分词形式）与 pin 行坐标块等；**lib.parser** 内 format2 解析统一处理表头/分隔线，避免列切片撕裂。
- Format2 的 port 行规则补齐：launch/capture 第三行 port 必须包含 `Delay`、`Time`、`Description`，并在 `Time` 与 `Description` 之间带边沿符号（`/` 或 `\`）；解析输出中 `trigger_edge` 必须为 `r/f`，`Description` 必须为 `<port_name> (in)`。
- `scripts/validate_extract_results.py` 新增 format2 port 专项校验：自动检查 launch/capture 中 port 行的 `Delay/Time` 数值合法性、`trigger_edge` 是否为 `r/f`、`Description` 是否符合 `<name> (in)` 约束，避免回归。
- `path_summary.csv` 新增 `clock_reconvergence_pessimism`、`clock_uncertainty` 两列，用于记录每条 path 的 clock reconvergence pessimism 与 clock uncertainty 增量；原先的 `uncertainty` 列已移除，统一使用 `clock_uncertainty`。
- reconvergence/uncertainty 的提取逻辑统一为「按关键词 + 数值顺序」：  
  - PT/format1：关键词在行首，数值在关键词后；从关键词后面的数值中取倒数第二个作为增量（Incr）；  
  - format2：关键词在行尾 Description 中，数值在左侧 Delay/Time 列；若关键词后无数值，则从关键词前的整行数值中取倒数第二个作为增量（Delay）。
- PT 生成器与解析器对 capture 段进行了对齐：capture_path 的最后一个点为 Endpoint 的时钟端 CK，`clock reconvergence pessimism` 与 `clock uncertainty` 只出现在 summary 段，不再混入 capture 点表。
- compare 统计新增固定误差分桶（`error_range_stats`）：
  - `arrival_time_ratio` / `required_time_ratio`：`[0,5)`, `[5,10)`, `[10,20)`, `[20,50)`, `>50`（按绝对值，单位 `%`）
  - `slack_diff`：`[0,5)`, `[5,10)`, `[10,20)`, `>20`（按绝对值）
  - HTML 汇总页按转置方式展示分桶占比：`arrival/required` 同表、`slack_diff` 单表。

### 推荐命令（不覆盖输出）

```bash
python -m lib gen-report config/gen_report/format1.yaml --seed 1
python -m lib gen-report config/gen_report/format2.yaml --seed 1
python -m lib gen-report config/gen_report/pt.yaml --seed 1
```

不指定 `-o` 时，默认输出分别为：
- `output/gen_format1_timing_report.rpt`
- `output/gen_format2_timing_report.rpt`
- `output/gen_pt_timing_report.rpt`
