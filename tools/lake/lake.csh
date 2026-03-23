# lake.csh：source 后可直接使用 `lake <command> ...`
#
# 用法：
#   source /path/to/tools/lake/lake.csh
#   lake compare -g ... -t ...
#
# 说明：
# - 本脚本默认将 tools/lake/bin 加入 PATH，并将 LAKE_PYTHON 固定在此处
# - `lake` 可执行脚本会从当前目录向上定位 repo root，再转发到 `python -m lib`

# 固定 Python 路径（请按实际环境修改为绝对路径更稳）
setenv LAKE_PYTHON python

# 将 tools/lake/bin 加入 PATH（csh 使用 path 数组）
# 尽量根据被 source 的脚本路径定位（$_ 通常为本脚本路径）。
set _lake_src = "$_"
set _lake_dir = ""
if ( "$_lake_src" != "" && -f "$_lake_src" ) then
  set _lake_dir = `cd \`dirname "$_lake_src"\`; pwd`
endif

set lake_bin = ""
if ( "$_lake_dir" != "" && -d "$_lake_dir/bin" ) then
  set lake_bin = "$_lake_dir/bin"
else if ( -d "tools/lake/bin" ) then
  set lake_bin = "tools/lake/bin"
else
  # 兜底：用户可手动改为绝对路径
  set lake_bin = "/path/to/timerExtract/tools/lake/bin"
endif

set found = 0
foreach p ( $path )
  if ( "$p" == "$lake_bin" ) set found = 1
end
if ( $found == 0 ) then
  set path = ( "$lake_bin" $path )
  rehash
endif

# lake 命令会直接走 PATH 里的可执行文件 `tools/lake/bin/lake`。
# 不建议再用 alias 覆盖，因为 alias 展开可能导致带空格/引号的参数（如 gen-pt 的 --extra "... "）被二次拆分。

