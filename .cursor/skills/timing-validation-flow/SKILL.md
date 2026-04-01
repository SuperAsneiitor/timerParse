---
name: timing-validation-flow
description: Build and execute a fixed timing validation flow for format1/format2/pt reports. Use when the user asks to validate three formats, run end-to-end generation and extraction, or compare format1/format2 against PT as golden.
---

# Timing Validation Flow

## Scope

Use this skill for standard end-to-end validation in this repo:

1. Generate 3 report formats (`format1`, `format2`, `pt`)
2. Extract 3 generated reports to CSV
3. Use PT summary as golden and compare:
   - `pt` vs `format1`
   - `pt` vs `format2`

## Required Output Layout

Always write artifacts to a timestamped directory:

- Base: `test_results/`
- Folder pattern: `test_results/validation_flow_YYYYMMDD_HHMMSS/`
- Subfolders:
  - `reports/`
  - `extract_format1/`
  - `extract_format2/`
  - `extract_pt/`
  - `compare/`

## Standard Commands

Preferred: run one fixed entrypoint from repo root:

```bash
python scripts/run_validation_flow.py --jobs 4
```

This script enforces timestamped output and executes the full chain (generate -> extract -> compare).

Manual equivalent (for debugging only):

```bash
python -m lib gen-report config/gen_report/format1.yaml --seed 101 -o test_results/<ts>/reports/gen_format1.rpt
python -m lib gen-report config/gen_report/format2.yaml --seed 202 -o test_results/<ts>/reports/gen_format2.rpt
python -m lib gen-report config/gen_report/pt.yaml      --seed 303 -o test_results/<ts>/reports/gen_pt.rpt

python -m lib extract test_results/<ts>/reports/gen_format1.rpt --format format1 -o test_results/<ts>/extract_format1 -j 4
python -m lib extract test_results/<ts>/reports/gen_format2.rpt --format format2 -o test_results/<ts>/extract_format2 -j 4
python -m lib extract test_results/<ts>/reports/gen_pt.rpt      --format pt      -o test_results/<ts>/extract_pt      -j 4

python -m lib compare test_results/<ts>/extract_pt/path_summary.csv test_results/<ts>/extract_format1/path_summary.csv -o test_results/<ts>/compare/pt_vs_format1.csv --stats-json test_results/<ts>/compare/pt_vs_format1_stats.json --no-charts --no-html
python -m lib compare test_results/<ts>/extract_pt/path_summary.csv test_results/<ts>/extract_format2/path_summary.csv -o test_results/<ts>/compare/pt_vs_format2.csv --stats-json test_results/<ts>/compare/pt_vs_format2_stats.json --no-charts --no-html
```

## Post-Change Validation (Required)

**After every code change** that touches report generation, parsing, or extraction, run the full validation and fix any failures immediately (no need to ask for permission):

```bash
python scripts/run_validation_flow.py --jobs 4
```

- If any step fails (gen-report, extract, or compare), fix the code and re-run until the flow completes successfully.
- Report row counts and compare stats to the user when reporting results.

### Full regression: non-LVF **and** LVF, each **100 paths** with **long data_path**

A complete end-to-end check must cover **both** tracks (they exercise different parsers / `--lvf` columns):

| Track | Entry script | What it enforces |
|-------|----------------|------------------|
| **Non-LVF** | `python scripts/run_validation_flow.py --jobs 4` | Uses `config/gen_report/base.yaml` **`num_paths: 100`** (and inherited by `format1.yaml` / `format2.yaml` / `pt.yaml`), so generated reports have **100 paths** with **long launch/data segments** from the normal generator. |
| **LVF** | `python scripts/run_lvf_100_validation.py` | Synthesizes **100** format1 **LVF** paths via `tests/format1_lvf_synth.py`, with **long `data_path`** (extra pin/net groups after the Startpoint output pin); runs `extract` and `extract-chaos` with **`--lvf`** and checks the five CSV row counts match. |

Run **both** after changes that could affect format1 LVF, launch/data split, or extract parity. The unit test `tests/test_lvf_100_paths.py` guards LVF 100-path parse + minimum `data_path_point_count`.

## Completion Checklist

- [ ] All 3 generated reports exist in `reports/`
- [ ] All 3 extract folders contain:
  - `launch_path.csv`
  - `capture_path.csv`
  - `launch_clock_path.csv`
  - `data_path.csv`
  - `path_summary.csv`
- [ ] Compare outputs exist:
  - `compare/pt_vs_format1.csv`
  - `compare/pt_vs_format2.csv`
- [ ] Compare stats JSON files exist
- [ ] （可选冒烟）`compare/detail_pt_vs_format1/compare_report.html` 与 `paths/path_*.html`（带 launch/capture 逐点对比）

## Reporting Format

When reporting to user, include:

- Base timestamped folder path
- Row counts for each extract (`launch/capture/summary`)
- Compare file paths (`pt_vs_format1`, `pt_vs_format2`)
- Any validation anomalies (if any)
