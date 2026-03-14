# 报告解析重构 — 提交并推送（在项目根目录执行）
# 用法: 在 timerParse 根目录执行 .\scripts\commit_and_push_refactor.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "=== 1. 检查 git 与变更 ==="
git status
git diff --stat

Write-Host "`n=== 2. 添加并提交 ==="
git add lib/parsers/time_parser_base.py lib/parsers/format1_parser.py lib/parsers/format2_parser.py lib/parsers/pt_parser.py lib/__init__.py lib/extract.py lib/cli.py tests/test_format1_parser.py tests/test_format2_parser.py tests/test_pt_parser.py scripts/commit_and_push_refactor.md scripts/commit_and_push_refactor.ps1
git commit -m "refactor(parsers): apply Python coding standards - camelCase, Chinese docstrings, single responsibility"

Write-Host "`n=== 3. 推送到 GitHub ==="
git push origin HEAD

Write-Host "`n完成。"
