# 报告解析重构 — 提交与推送说明

在项目根目录执行以下命令完成提交并推送到 GitHub。

## 1. 查看变更

```bash
git status
git diff --stat
```

## 2. 添加并提交

```bash
git add -A
git status
git commit -m "你的提交说明"
```

> 说明：解析代码现位于 **`lib/parser_V2/`**（已移除历史 `lib/parsers/`）。提交前请 `git status` 确认暂存范围。

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
python -m unittest discover -s tests -p "test_*.py" -q
# 可选：python scripts/run_validation_flow.py --jobs 2
```
