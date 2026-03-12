# 测试结果统一存放目录

本目录用于存放**所有测试运行产物**，便于复现与对比。

## 约定

- **时间戳**：后续每次测试产生的文档/报告均在**文件名或子目录名**中带测试时间戳，格式：`YYYYMMDD_HHMMSS`（例如 `20260310_143022`）。
- **子目录**：建议按任务建子目录，例如：
  - `extract_20260310_143022/`：某次 extract 的 CSV 输出
  - `compare_20260310_144100/`：某次 compare 的对比结果与图表
  - `gen_report_20260310_145000/`：某次 gen-report 生成的报告
- **本目录已加入 .gitignore**，不会提交到仓库；仅保留本 README 的说明。

## 示例命令（带时间戳输出）

```bash
# 使用时间戳作为输出子目录
set TS=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
python -m lib extract input/report.rpt -o test_results/extract_%TS%
python -m lib gen-report config/timing_report_format2_example.yaml -o test_results/gen_report_%TS%/gen.rpt
```

或使用脚本 `scripts/run_tests_with_timestamp.py`（若已提供）自动带时间戳写入本目录。
