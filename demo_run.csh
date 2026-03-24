#!/bin/csh -f

# Demo flow (DO NOT auto-run):
# 1) 解析单一格式 timing report（format1 或 format2）
# 2) 将 launch_path.csv 转成 PT report_timing TCL，并在 PT 中执行
# 3) 解析 PT 输出并与原格式 path_summary 做对比

set ROOT = `pwd`
set RUN_TAG = `date +%Y%m%d_%H%M%S`
set OUT_BASE = "$ROOT/output/demo_flow_$RUN_TAG"

# ===== 阶段0：选择输入格式（只跑一种） =====
# 可选: format1 / format2
set TARGET_FORMAT = "format1"

if ("$TARGET_FORMAT" == "format1") then
    set INPUT_RPT = "$ROOT/input/format_1.timing_report.txt"
else if ("$TARGET_FORMAT" == "format2") then
    set INPUT_RPT = "$ROOT/input/format_2.timing_report.rpt.txt"
else
    echo "Error: TARGET_FORMAT must be format1 or format2"
    exit 1
endif

# Optional PT runtime settings (can be overridden before running this script):
#   setenv PT_BIN pt_shell
#   setenv PT_SETUP /path/to/pt_setup.tcl
if (! $?PT_BIN) then
    setenv PT_BIN pt_shell
endif
if (! $?PT_SETUP) then
    setenv PT_SETUP ""
endif

# ===== 阶段1：准备输出目录 =====
echo "== Prepare output folders =="
mkdir -p "$OUT_BASE/source_extract"
mkdir -p "$OUT_BASE/pt_run"
mkdir -p "$OUT_BASE/pt_extract"
mkdir -p "$OUT_BASE/compare"

# ===== 阶段2：解析原始报告（format1 或 format2）=====
echo "== Step1: Extract source report ($TARGET_FORMAT) =="
python -m lib extract "$INPUT_RPT" --format "$TARGET_FORMAT" -o "$OUT_BASE/source_extract"
if ($status != 0) exit 1

# ===== 阶段3：根据 launch_path.csv 生成 PT TCL =====
echo "== Step2: Generate PT report_timing TCL =="
python -m lib gen-pt "$OUT_BASE/source_extract/launch_path.csv" \
    -o "$OUT_BASE/pt_run/report_timing.tcl" \
    --report-file "$OUT_BASE/pt_run/pt_report.rpt" \
    --extra "-delay_type max -path_type full_clock"
if ($status != 0) exit 1

# ===== 阶段4：封装 PT 执行脚本并运行 =====
echo "== Step3: Build PT runner TCL wrapper =="
cat > "$OUT_BASE/pt_run/run_in_pt.tcl" << EOF
if {[string length "$PT_SETUP"] > 0 && [file exists "$PT_SETUP"]} {
    source "$PT_SETUP"
}
source "$OUT_BASE/pt_run/report_timing.tcl"
quit
EOF

echo "== Step4: Run PrimeTime =="
"$PT_BIN" -f "$OUT_BASE/pt_run/run_in_pt.tcl" > "$OUT_BASE/pt_run/pt_run.log" 2>&1
if ($status != 0) exit 1

# ===== 阶段5：解析 PT 输出报告 =====
echo "== Step5: Extract PT report =="
python -m lib extract "$OUT_BASE/pt_run/pt_report.rpt" --format pt -o "$OUT_BASE/pt_extract"
if ($status != 0) exit 1

# ===== 阶段6：对比 path_summary（PT vs 原格式）=====
echo "== Step6: Compare source vs PT =="
python -m lib compare \
    "$OUT_BASE/source_extract/path_summary.csv" \
    "$OUT_BASE/pt_extract/path_summary.csv" \
    -o "$OUT_BASE/compare/pt_vs_${TARGET_FORMAT}.csv" \
    --stats-json "$OUT_BASE/compare/pt_vs_${TARGET_FORMAT}_stats.json" \
    --no-charts --no-html
if ($status != 0) exit 1

echo ""
echo "Demo flow done."
echo "Target format: $TARGET_FORMAT"
echo "Output base: $OUT_BASE"
echo "Compare file: $OUT_BASE/compare/pt_vs_${TARGET_FORMAT}.csv"
