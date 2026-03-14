# 报告解析重构 — 提交与推送说明

在项目根目录执行以下命令完成提交并推送到 GitHub。

## 1. 查看变更

```bash
git status
git diff --stat
```

## 2. 添加并提交

```bash
git add lib/parsers/time_parser_base.py lib/parsers/format1_parser.py lib/parsers/format2_parser.py lib/parsers/pt_parser.py lib/__init__.py lib/extract.py lib/cli.py tests/test_format1_parser.py tests/test_format2_parser.py tests/test_pt_parser.py
git commit -m "refactor(parsers): apply Python coding standards — camelCase, Chinese docstrings, single responsibility

- time_parser_base: rename to camelCase (parseReport, splitLaunchByCommonPin, writeCsv, etc.), add module/function docstrings
- format1_parser: scanPathBlocks, parseOnePath, extractColumnPositions, parseFixedWidthAttrs, applyTypeFilter, buildPointRow; split parseOnePath into _fillMetaFromHeader, _findTableStart, _parseLaunchSegment, _parseCaptureSegment
- format2_parser: same renames + _parseLineByType, _parseInputPin, _parseOutputPin, etc.
- pt_parser: parseOnePath and base method calls
- lib/__init__: createParser, detectReportFormat
- extract: runExtract, parseWithJobs, _workerParseOne, createParser/detectReportFormat/writeCsv
- cli: runExtract
- tests: parse_report -> parseReport"
```

## 3. 推送到 GitHub

若已配置 remote：

```bash
git push origin HEAD
```

若尚未添加 remote（替换为你的仓库地址）：

```bash
git remote add origin https://github.com/SuperAsneiitor/timerParse.git
git push -u origin HEAD
```

## 4. 验证（提交前建议执行）

```bash
python -m pytest tests/ -v --tb=short
python scripts/run_validation_flow.py --jobs 2
```
