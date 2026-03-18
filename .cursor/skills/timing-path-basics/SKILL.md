---
name: timing-path-basics
description: Explain timing path fundamentals (launch/capture structure, setup/hold formulas, slack rules) and map them to PrimeTime-style report sections. Use when users ask about STA timing path basics, PT report fields, data arrival/required/slack meaning, or report format validation/generation.
---

# Timing Path Basics

## Scope

Use this skill when working with STA timing-path questions or PT-style report generation:
- timing path structure (launch clock path, data path, capture clock path, summary)
- metric meaning (`Incr`, `Path` / `Delay`, `Time`, `data arrival time`, `data required time`, `slack`)
- setup/hold rules and sign conventions
- clock uncertainty / reconvergence pessimism and their impact on required time
- format validation against PrimeTime-like reports

## Core Concepts

### Path Structure（从第一性原理出发，PT-like）

1. **Header（路径级元信息）**
   - `Startpoint`, `Endpoint`
   - trigger relation text (clocked by which clock edge)
   - `Last common pin` (common point between launch and capture portions)
   - `Path Group`, `Path Type`

2. **Launch path**
   - **Launch clock path**：clock 源 → 时钟树 → launch FF/port 的 CK
     - 报告中对应 `clock ... (rise/fall edge)`、`clock source latency`、clock network delay 等行
   - **Port / boundary**：可选的 port 行（如 `dft_clk (in)`），表示时钟/数据跨越 IO 边界的位置
   - **Data path（launch 侧）**：launch FF Q / 输入端口 → 组合逻辑 → 直到到达 capture 端的“数据检查点”
     - 在点表中体现为按 **`input_pin → output_pin → net`** 循环出现的一串 stdcell + net
   - 末尾以 `data arrival time` 行收尾

3. **Capture path**
   - **Capture clock path**：clock 源 → 时钟树 → capture FF/端口的 CK
   - Optional port section（端口 CK）及 Last common pin
   - 之后也是一串 stdcell + net（`input_pin → output_pin → net` 循环），直到 endpoint 的 input pin
   - 在尾部包含：
     - `clock reconvergence pessimism`（CRPR/CPPR 调整）
     - `clock uncertainty`
     - `library setup/hold time`
   - 最终给出 `data required time`

4. **Summary**
   - separator
   - `data arrival time`
   - `data required time`
   - separator
   - optional `statistical adjustment`
   - `slack (MET|VIOLATED)`

### Metric Meanings（路径内及路径级）

- **Incr（增量）**：当前行（当前 cell/net）的增量延迟。
- **Path（累计）**：从段首（例如 startpoint 附近）到当前行为止的累计延迟；在 format1/pt 中一般满足 `Path = cumsum(Incr)`。
- **Delay / Time（format2）**：`Delay` 是当前行增量延迟，`Time` 是段内累计时间，满足 `Time = cumsum(Delay)`。
- **data arrival time**：数据真正到达检查点（capture FF D 或输出端口）的时间，通常 = launch clock 到达 + data path 延迟（考虑 CRPR/uncertainty 之前/之后的计法）。
- **data required time**：为了满足 setup/hold 约束，数据**最迟/最早**必须到达的时间，通常 = capture clock 边沿时间 − setup/hold 要求 − clock uncertainty − reconvergence pessimism 等。
- **slack**：路径在当前 corner/约束下的 timing 裕量，一般定义为 `required_time − arrival_time`（为正表示 MET，为负表示 VIOLATED）。
- **clock reconvergence pessimism**：由于 launch/capture 时钟路径共享公共段且被分别用不同最坏/最好条件分析而引入的“重复保守量”，CRPR 会将其从最终延迟中扣除。
- **clock uncertainty**：来自 jitter、PLL 噪声、建模误差等的不确定性，直接收紧 required_time，减小 slack。

### Common Formulas

- **Setup slack**: `slack = required - arrival`
- **Hold slack**: often represented with equivalent sign-convention transforms in reports; keep report consistency:
  - use one sign convention consistently for arrival/required
  - ensure displayed `slack` matches displayed arrival/required semantics
- `slack >= 0` -> `MET`; `slack < 0` -> `VIOLATED`

## PT-Format Validation Checklist

- [ ] Header includes start/end and edge-trigger clock text.
- [ ] `Last common pin` exists in header and appears as an actual point in capture path.
- [ ] Launch path clock 段与 data 段清晰分开：clock 段到 port/边界为止，之后为 stdcell data 段（input/output/net 周期）。
- [ ] Capture path 同样包含 clock 段 + data 段，并以 endpoint input pin 收尾。
- [ ] Separator positions match target format (header/body boundaries and summary boundaries).
- [ ] Summary block order matches target template (`arrival`, `required`, then slack block if required).
- [ ] `Path` is cumulative and internally consistent with `Incr`.
- [ ] `slack` label (`MET/VIOLATED`) matches numeric sign.

## Comparing Two Timing Tools on the Same Path

When comparing a golden report and a test report for **the same physical timing path**, focus on:

- **Path-level metrics**:
  - `arrival_time`, `required_time`, `slack`
  - `launch_clock_delay`, `data_path_delay`
  - `clock_reconvergence_pessimism`, `clock_uncertainty`
- **Segment-level drill-down**:
  - On launch/capture clock segments: compare key clock nodes' `Incr` to see clock-tree modeling differences.
  - On data path: compare the top-K cells/nets with the largest `Incr/Delay` differences.
- **Electrical metrics for root-cause**:
  - `Fanout`, `Cap`, `Trans`, `Derate` on the segments where `Incr/Delay` differs most.

Use this interpretation:

- If `launch_clock_delay` differs while `data_path_delay` is similar → 时钟建模或 CRPR/uncertainty 处理不同。
- If `data_path_delay` 差异大 → 组合逻辑/布线 RC / derate / library 模型有差异。
- If `clock_reconvergence_pessimism` 或 `clock_uncertainty` 差异大 → slack 差来自时钟侧的保守量建模不同。

## Output Guidance

When answering users:
- First state whether structure is aligned or not.
- Then list exact mismatches by section: header / launch / capture / summary.
- Provide concrete fix actions in generation config and rendering logic.
- Keep terminology fixed: always use “launch path”, “capture path”, “arrival/required/slack”.

## Test Result Storage Convention

When running extraction/validation tests, always store outputs under a timestamped directory:

- Base directory: `test_results/`
- Naming pattern: `test_results/<task_name>_YYYYMMDD_HHMMSS/`
- Keep raw/generated outputs separated by format, for example:
  - `raw_format1/`, `raw_format2/`, `raw_pt/`
  - `gen_format1/`, `gen_format2/`, `gen_pt/`

Recommended command style:

```bash
python -m lib extract <report.rpt> --format <format> -o test_results/<task>_<timestamp>/<subdir>
```

