---
name: test-validation-rules
description: Test and validation output conventions for timerExtract. Use when writing test results, running validation, or changing report/parser code.
---

# Test & Validation Rules

## Output Directory Convention

All test and validation artifacts **must** be written under **timestamped directories** only:

- **Base path**: `test_results/`
- **Pattern**: `test_results/<prefix>_YYYYMMDD_HHMMSS/` (e.g. `validation_flow_20260316_105205`, `extract_parallel_validation_20260316_100327`)
- **Do not** create non-timestamped folders or files under `test_results/` (e.g. avoid `test_results/tmp_*`, `test_results/format2_launch_sep`, or fixed-name `.rpt` files for persistent storage).

One-off or ad-hoc runs must also use a timestamped subdir, for example:

```bash
TS=$(date +%Y%m%d_%H%M%S)
python -m lib gen-report config/gen_report/format2.yaml --seed 1 -o "test_results/validation_flow_${TS}/reports/gen_format2.rpt"
python -m lib extract "test_results/validation_flow_${TS}/reports/gen_format2.rpt" --format format2 -o "test_results/validation_flow_${TS}/extract_format2"
```

On Windows (PowerShell):

```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
python -m lib gen-report config/gen_report/format2.yaml --seed 1 -o "test_results/validation_flow_$ts/reports/gen_format2.rpt"
```

## Post-Change Validation (Required)

**After every code change** that affects report generation, parsing, or extraction:

1. Run the **non-LVF** full validation flow from repo root ( **`num_paths: 100`** in `config/gen_report/base.yaml` → **100 paths** with long timing segments ):
   ```bash
   python scripts/run_validation_flow.py --jobs 4
   ```
2. For changes touching **format1 LVF**, launch/data split, or `--lvf` extract, also run the **LVF 100-path long `data_path`** script (synthetic report + `extract` / `extract-chaos` with `--lvf`):
   ```bash
   python scripts/run_lvf_100_validation.py
   ```
   Optional: `--extra-data-groups N` matches `tests/format1_lvf_synth.buildFormat1LvfReport(..., extra_data_groups=N)` to stress longer data paths.
3. If any step fails (gen-report, extract, or compare), fix the code and re-run until the flow completes successfully. Do not wait for user approval to fix.
4. When reporting results, include: base timestamped folder path, row counts per format, and compare stats (or any anomalies).

**Rule of thumb:** a **complete** regression run = **`run_validation_flow.py`** (non-LVF, 100 paths) **+** **`run_lvf_100_validation.py`** (LVF, 100 paths, long data_path). Unit test `tests/test_lvf_100_paths.py` complements the LVF track.

## Completion Checklist (per run)

- [ ] All 3 reports generated under `reports/`
- [ ] All 3 extract dirs contain: `launch_path.csv`, `capture_path.csv`, `launch_clock_path.csv`, `data_path.csv`, `path_summary.csv`
- [ ] Compare outputs: `compare/pt_vs_format1.csv`, `compare/pt_vs_format2.csv` (and stats JSON)

## Cleanup (Optional)

To avoid clutter, consider periodically removing old timestamped dirs or non-timestamped leftovers under `test_results/` (e.g. `tmp_*`, fixed-name folders). Prefer keeping only recent validation runs.
