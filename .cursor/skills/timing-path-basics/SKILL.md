---
name: timing-path-basics
description: Explain timing path fundamentals (launch/capture structure, setup/hold formulas, slack rules) and map them to PrimeTime-style report sections. Use when users ask about STA timing path basics, PT report fields, data arrival/required/slack meaning, or report format validation/generation.
---

# Timing Path Basics

## Scope

Use this skill when working with STA timing-path questions or PT-style report generation:
- timing path structure (launch path, capture path, summary)
- metric meaning (`Incr`, `Path`, `data arrival time`, `data required time`, `slack`)
- setup/hold rules and sign conventions
- format validation against PrimeTime-like reports

## Core Concepts

### Path Structure (PT-like)

1. **Header**
   - `Startpoint`, `Endpoint`
   - trigger relation text (clocked by which clock edge)
   - `Last common pin` (common point between launch and capture portions)
   - `Path Group`, `Path Type`

2. **Launch path**
   - clock section (`clock ... (rise/fall edge)`, source/network latency)
   - optional port section (`port (in)`, port net)
   - launch clock path points (often repeated groups of input/output/net)
   - data path points (repeated groups of input/output/net)
   - endpoint and `data arrival time`

3. **Capture path**
   - clock section
   - optional port section
   - repeated point groups (input/output/net), including the common pin
   - endpoint
   - checks/adjustments (e.g. reconvergence pessimism, uncertainty, setup/hold time)
   - `data required time`

4. **Summary**
   - separator
   - `data arrival time`
   - `data required time`
   - separator
   - optional `statistical adjustment`
   - `slack (MET|VIOLATED)`

### Metric Meanings

- **Incr**: incremental delay contribution of current row/point.
- **Path**: cumulative delay at current row; commonly `Path = cumsum(Incr)` inside each section.
- **data arrival time**: effective arrival at capture check point (often shown with report-specific sign convention).
- **data required time**: required timing limit for the check (setup/hold dependent).
- **slack**: margin to constraint.

### Common Formulas

- **Setup slack**: `slack = required - arrival`
- **Hold slack**: often represented with equivalent sign-convention transforms in reports; keep report consistency:
  - use one sign convention consistently for arrival/required
  - ensure displayed `slack` matches displayed arrival/required semantics
- `slack >= 0` -> `MET`; `slack < 0` -> `VIOLATED`

## PT-Format Validation Checklist

- [ ] Header includes start/end and edge-trigger clock text.
- [ ] `Last common pin` exists in header and appears as an actual point in capture path.
- [ ] Launch path contains repeated point groups (input/output/net), not single isolated points.
- [ ] Capture path contains repeated point groups and endpoint.
- [ ] Separator positions match target format (header/body boundaries and summary boundaries).
- [ ] Summary block order matches target template (`arrival`, `required`, then slack block if required).
- [ ] `Path` is cumulative and internally consistent with `Incr`.
- [ ] `slack` label (`MET/VIOLATED`) matches numeric sign.

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

