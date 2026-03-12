# Timing 报告三种格式对比与验证

本文档对比 **format1**、**format2**、**pt** 三种真实报告的结构，说明生成器输出与真实报告在格式上的一致性及属性累加关系。

---

## 1. 格式结构对比

| 项目 | format1 (APR) | format2 | pt (PrimeTime) |
|------|----------------|--------|-----------------|
| **Title 形式** | `  Startpoint: ...`<br>`  Endpoint: ...`<br>`  Common Pin: ...`<br>`  Scenario: ...`<br>`  Path Group: ...`<br>`  Path Type: ...` | `  Scenario                :  value`<br>`  Path Start              :  value`<br>`  Path End                :  value`<br>`  Common Pin         :  value`<br>`  Group Name          :  value`<br>`  Analysis Type         :  value` | `  Startpoint: ...`（可多行）<br>`  Endpoint: ...`（可多行）<br>`  Path Group: ...`<br>`  Path Type: ...` |
| **表头列** | Point, Fanout, Cap, Trans, Location, Incr, Path | Type, Fanout, Cap, D-Trans, Trans, Derate, x-coord, y-coord, D-Delay, Delay, Time, Description | Point, Fanout, Cap, Trans, Derate, Incr, Path |
| **首列** | Point（点名一整列） | Type（clock/pin/net/…） | Point（点名一整列） |
| **累加关系** | **Path = cumsum(Incr)** | **Time = cumsum(Delay)** | **Path = cumsum(Incr)** |
| **trigger** | Path 列末位 r/f | Description 前 `/` 或 `\` 表示 r/f | Path 列末位 r/f |

---

## 2. 属性累加关系（生成器已实现）

- **format1 / pt**：每行有 `Incr`（本段增量），`Path` 为从段首到当前行的 **Incr 累加和**。生成器在 `path_table` 中默认 `cumulative_rules: { Path: Incr }`，按段（launch / capture）分别累加后填入 Path。
- **format2**：每行有 `Delay`（本段延迟），`Time` 为从段首到当前行的 **Delay 累加和**。生成器默认 `cumulative_rules: { Time: Delay }`，按段累加后填入 Time。

YAML 中可通过 `path_table.cumulative_rules` 覆盖，例如：

```yaml
path_table:
  cumulative_rules: { Time: Delay }   # format2
  # 或
  cumulative_rules: { Path: Incr }   # format1 / pt
```

---

## 3. 生成器与真实报告格式差异说明

| 格式 | 生成器支持 | 与真实报告差异 |
|------|------------|----------------|
| **format2** | 完整支持：Title（Scenario, Path Start, Path End, Common Pin, Group Name, Analysis Type）、表头与列顺序、Type/Fanout/Cap/Delay/Time/Description、累加 Time=cumsum(Delay)、分隔线。 | 可选：x-coord/y-coord 为 `{ x y }` 或纯数字由配置决定；Description 中 `/`、`\` 与 trigger 的对应关系与真实报告一致。 |
| **format1** | 支持 Title（Startpoint, Endpoint, Common Pin, Scenario, Path Group, Path Type）、表头 Point + Fanout/Cap/Trans/Location/Incr/Path、Path=cumsum(Incr)。 | 需在 YAML 中配置 column_order 为 format1 列顺序；Point 列由 Description/point 提供；真实报告中 “Point” 为整列点名，生成器用统一列配置输出。 |
| **pt** | 支持 Title（Startpoint, Endpoint, Path Group, Path Type）、表头 Point + Fanout/Cap/Trans/Derate/Incr/Path、Path=cumsum(Incr)。 | Startpoint/Endpoint 多行样式可选；列顺序与 format1 类似但无 Location、有 Derate。 |

---

## 4. 验证方式

1. **生成**：用对应 YAML 生成三种格式报告（见 `config/gen_report/format1.yaml`、`config/gen_report/format2.yaml`、`config/gen_report/pt.yaml`）。
2. **解析**：对生成报告执行 `python -m lib extract <gen.rpt> -o <out_dir> --format <format1|format2|pt>`，确认能解析且 CSV 行数、path 数合理。
3. **累加检查**：对解析得到的 launch_path / capture_path CSV，检查 Path 列（format1/pt）或 Time 列（format2）是否等于同段内 Incr 或 Delay 的逐行累加。

测试结果统一存放于 `test_results/`，文件名或子目录带时间戳（见 test_results/README.md）。

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
