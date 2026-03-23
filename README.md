# timerExtract

**用途**：把 Timing 报告解析成 CSV（每条 path 的 launch/capture 点表与 `path_summary`）；可选生成 PrimeTime `report_timing` 脚本、对比两份 `path_summary`。

本文档只说明**你怎么用**：装什么、从哪进命令、各子命令干什么、典型一条命令怎么写。实现细节、格式约定、YAML 模板说明见 **[docs/](docs/)**；旧版超长说明已迁至 **[docs/README_legacy.md](docs/README_legacy.md)**。

---

## 1. 使用前准备

1. **克隆仓库**并在本机安装 **Python 3**（具体最低版本以你环境为准；开发常用 3.8+）。
2. **依赖**（按用到的功能装）：
   - `gen-report` 需要：`pip install pyyaml`
   - `compare` 出图需要：`matplotlib`（可选；未装时可能跳过图表）
3. **工作目录**：以下命令假设你在**本仓库目录内**或其子目录执行（`lake` 会向上找仓库根；`python -m lib` 建议在仓库根执行，或保证 `PYTHONPATH` 能找到 `lib`）。

**说明**：仓库默认不把大体积测试数据/本地输出纳入版本控制（见 `.gitignore`）。请自备 `.rpt` 等输入，并把输出指到你自己的目录。

---

## 2. 怎么调用：推荐 `lake`（csh/tcsh）

在 **csh/tcsh** 中 source 一次，之后直接用 `lake`：

```csh
source /path/to/timerExtract/tools/lake/lake.csh
lake <子命令> [参数...]
```

- **解释器**：可在 `tools/lake/lake.csh` 里设置环境变量 **`LAKE_PYTHON`**（默认 `python`）。
- **行为**：`lake` 会从当前目录**向上查找**仓库根（含 `.git` 或 `lib/cli.py`），在根目录执行 **`python -m lib <子命令> ...`**。

**等价写法**（不依赖 csh，在仓库根执行）：

```bash
python -m lib <子命令> [参数...]
```

---

## 3. 帮助与全局选项

```bash
python -m lib
python -m lib extract -h
python -m lib compare -h
```

所有子命令都支持：

| 选项 | 含义 |
|------|------|
| `-l brief` | 日志：每步一行摘要（默认） |
| `-l full` | 日志：多行展开（路径、行数等） |

---

## 4. 兼容：省略子命令时默认是 `extract`

若第一个参数**不是**下面列出的子命令名，会自动当作 **`extract`**：

```bash
lake path/to/report.rpt -o path/to/out
# 等价于
lake extract path/to/report.rpt -o path/to/out
```

---

## 5. 子命令一览（你要做的事 → 用什么命令）

| 子命令 | 典型用途 |
|--------|----------|
| `extract` | 解析**一份** timing 报告 → 输出多份 CSV |
| `extract-chaos` | 用 **parser_chaos** 流水线解析同一份报告（多进程队列；大文件可分片输出） |
| `gen-pt` | 从 `launch_path.csv` 生成 PrimeTime **`report_timing` TCL** |
| `compare` | 对比两份 **`path_summary.csv`**（golden vs test），可选 HTML/图表 |
| `gen-report` | 按 **YAML** 生成合成 timing 报告（`.rpt`） |

完整参数见下文 **第 10 节**；与 `python -m lib <子命令> -h` 一致。

---

## 6. 最小示例（复制即用）

下面路径请换成你自己的文件。

### 6.1 解析报告 → CSV

```bash
lake extract input/report.rpt -o output/extract -f auto -j 4
```

常用输出（在 `-o` 目录下）：`launch_path.csv`、`capture_path.csv`、`path_summary.csv` 等。

大文件按 path 分片（每 N 条一组 `*_partK.csv`，并合并 `path_summary.csv`）：

```bash
lake extract input/report.rpt -o output/extract -j 4 -p 10000
# 可选：分片时额外合并 launch_path.csv
lake extract input/report.rpt -o output/extract -j 4 -p 10000 -m
```

### 6.2 parser_chaos 解析（可选）

```bash
lake extract-chaos input/report.rpt -o output/chaos -f auto -j 4
```

更多说明见 [docs/parser_chaos.md](docs/parser_chaos.md)。

### 6.3 生成 PrimeTime `report_timing` TCL

```bash
lake gen-pt output/extract/launch_path.csv -o output/report_timing.tcl --output-file output/pt_report.rpt
```

- **`-o`**：生成的 TCL 文件路径。
- **`--output-file`**：写入 TCL 的 `set output_file "..."`（PrimeTime 里 `report_timing ... >> ${output_file}` 的目标路径；**优先于** `-r/--report-file`）。
- **`-g "glob"`**：多个 `launch_path_part*.csv` 一次读入时可用通配。

### 6.4 对比 path_summary

```bash
lake compare -g golden/path_summary.csv -t test/path_summary.csv -o output/compare/result.csv --no-charts --no-html
```

需要汇总页/图表/详情页时，去掉 `--no-charts`、`--no-html`，并可按 `-h` 附加 `--golden-launch-csv` 等。

### 6.5 用 YAML 生成合成报告

```bash
lake gen-report config/gen_report/format2.yaml -o output/gen.rpt -s 42
```

---

## 7. 进阶与格式细节（不在 README 展开）

| 文档 | 内容 |
|------|------|
| [docs/FORMAT_VALIDATION.md](docs/FORMAT_VALIDATION.md) | 格式、字段、校验约定 |
| [docs/parser_chaos.md](docs/parser_chaos.md) | parser_chaos 流程 |
| [docs/SESSION_MIGRATION.md](docs/SESSION_MIGRATION.md) | 会话/环境迁移提示 |
| [docs/README_legacy.md](docs/README_legacy.md) | 旧版 README 全文（参数表、YAML 细节、目录结构等） |

---

## 8. 依赖一览

| 用途 | 包 |
|------|-----|
| `gen-report` | `pyyaml` |
| `compare` 图表（可选） | `matplotlib` |

---

## 9. 开发者：运行测试（可选）

```bash
python -m unittest tests.test_format1_parser tests.test_format2_parser tests.test_pt_parser tests.test_gen_pt_report_timing tests.test_compare_path_summary -v
```

测试产物建议写入 `test_results/`（见 `test_results/README.md`）。

---

## 10. 命令参数详解（与 lib/cli.py 一致）

**`lake` 与 `python -m lib`**：子命令及其后的参数**完全一致**（同一套 argparse）。`lake` 会先切换到仓库根目录再执行 `python -m lib`；相对路径以仓库根为基准。解释器由 `LAKE_PYTHON` 控制（见 `tools/lake/lake.csh`）。

以下凡写 `lake <子命令> ...`，均可替换为 `python -m lib <子命令> ...`。

### 10.1 所有子命令共有

| 选项 | 说明 |
|------|------|
| `-l brief` / `--log-level brief` | 日志：每步一行摘要（默认） |
| `-l full` / `--log-level full` | 日志：多行展开（路径、行数等） |

### 10.2 `extract`

| 参数 | 说明 |
|------|------|
| `input_rpt` | 输入 timing report 文件路径（位置参数） |
| `-o` / `--output-dir` | 输出目录（默认 `output_lib`） |
| `-f` / `--format` | `auto` \| `format1` \| `format2` \| `pt` \| `apr`（默认 `auto`） |
| `-j` / `--jobs N` | 并行 worker 数（默认 1） |
| `-p` / `--paths-per-shard N` | 每 N 条 path 一组 `*_partK.csv`（0=不拆分，默认 0） |
| `-m` / `--merge-launch` | 分片输出时额外合并生成 `launch_path.csv`（开关） |

### 10.3 `extract-chaos`

| 参数 | 说明 |
|------|------|
| `input_rpt` | 输入 timing 报告文件路径（位置参数） |
| `-o` / `--output-dir` | 输出目录（默认 `output_parser_chaos`） |
| `-f` / `--format` | `auto` \| `format1` \| `format2` \| `pt` \| `apr`（默认 `auto`） |
| `-j` / `--jobs N` | 解析器 Worker 进程数（默认 **3**） |
| `-p` / `--paths-per-shard N` | 每 N 条 path 一组 `*_partK.csv`（0=不拆分） |
| `-m` / `--merge-launch` | 分片输出时额外合并 `launch_path.csv`（开关） |

### 10.4 `gen-pt`

| 参数 | 说明 |
|------|------|
| `launch_csv` | `launch_path.csv` 路径（可选位置参数，默认 `output/launch_path.csv`） |
| `-o` / `--output` | 输出 TCL 路径（默认 `output/report_timing.tcl`） |
| `-n` / `--max-paths N` | 仅前 N 条 path（0=全部） |
| `-w` / `--no-wrap` | 每条 `report_timing` 单行输出（开关） |
| `-e` / `--extra ARGS` | 额外 `report_timing` 参数，原样拼到命令末尾 |
| `-r` / `--report-file RPT` | TCL 中 `report_file` 文件名（默认 `report_file.rpt`） |
| `--output-file RPT_PATH` | `report_timing` 重定向输出文件路径（**覆盖** `-r/--report-file`） |
| `-rise_cmd FLAG` | 上升沿 through 参数名（默认 `-rise_through`） |
| `-fall_cmd FLAG` | 下降沿 through 参数名（默认 `-fall_through`） |
| `-g` / `--launch-glob GLOB` | 多个 launch CSV 通配读取（优先级高于位置参数 `launch_csv`） |
| `-j` / `--jobs N` | 多进程 worker 数（默认 1） |

### 10.5 `compare`

| 参数 | 说明 |
|------|------|
| `golden_file` | （兼容）Golden `path_summary.csv`（可选位置参数） |
| `test_file` | （兼容）Test `path_summary.csv`（可选位置参数） |
| `-g` / `--golden-file` | Golden `path_summary.csv`（推荐） |
| `-t` / `--test-file` | Test `path_summary.csv`（推荐） |
| `-o` / `--output` | 输出对比 CSV 路径（未指定时默认写到 golden 同目录 `compare_result.csv`） |
| `-T` / `--threshold` | 阈值统计条件（默认 `10.0`，对应 help 中 10% 语义） |
| `-b` / `--bins` | 直方图桶数（默认 50） |
| `-c` / `--charts-dir` | 图表输出目录（默认 `<输出目录>/charts`） |
| `-C` / `--no-charts` | 禁用图表（开关） |
| `-H` / `--no-html` | 禁用 HTML 报告（开关） |
| `-s` / `--stats-json` | 统计 JSON 路径 |
| `-S` / `--stats-csv` | 统计 CSV 路径（可选） |
| `--match-by` | `path_id`（默认）或 `signature` |
| `--golden-launch-csv PATH` | golden 侧 `launch_path.csv`（与 test 同时指定时用于详情页 launch 逐点） |
| `--test-launch-csv PATH` | test 侧 `launch_path.csv` |
| `--golden-capture-csv PATH` | golden 侧 `capture_path.csv` |
| `--test-capture-csv PATH` | test 侧 `capture_path.csv` |
| `--page-size N` | HTML 路径列表分页大小（默认 100） |
| `--sort-by COL` | HTML 路径列表排序字段（默认 `slack_ratio`） |
| `--no-sort-abs` | 关闭按绝对值排序（默认按绝对值降序） |
| `--detail-scope` | `none` \| `first_page`（默认）\| `all` |

### 10.6 `gen-report`

| 参数 | 说明 |
|------|------|
| `config` | YAML 配置文件路径（位置参数） |
| `-o` / `--output` | 输出 `.rpt` 路径（默认按 format 写到 `output/gen_<format>_timing_report.rpt`） |
| `-s` / `--seed N` | 随机种子（可复现） |
