#!/usr/bin/env bash
# 把 export-session.sh 导出的会话 bundle 导入本机部署，让它在应用里真的出现。
#
# 为什么需要它：导出的是"归档文本"，应用的会话列表读的是 <DSH_HOME>/sessions/。
# 直接拷文件进去不会上屏——目录名是按 cwd 编码的，元数据也另存一处，路径还是原作者的。
# 本脚本负责：改写路径 -> 按编码规则放正文 -> 补元数据 -> 还原产出的文档。
#
# 用法：
#   bash deploy/scripts/import-session.sh <bundle 目录> [DSH_HOME]
# 环境变量：
#   WORKDSH_TOOLS_VENV  放 zstandard 的 venv，默认 $HOME/.venvs/workdsh-tools
#   DRY_RUN=1           只打印不落盘
set -euo pipefail

BUNDLE="${1:-}"
DSH_HOME="${2:-$HOME/workdsh/.test-runtime/preview}"
VENV="${WORKDSH_TOOLS_VENV:-$HOME/.venvs/workdsh-tools}"

[ -n "$BUNDLE" ] || { echo "✗ 用法: import-session.sh <bundle 目录> [DSH_HOME]"; exit 1; }
[ -d "$BUNDLE" ] || { echo "✗ bundle 不存在: $BUNDLE"; exit 1; }
[ -f "$BUNDLE/manifest.json" ] || { echo "✗ 缺 manifest.json（不是 export-session.sh 导出的 bundle？）"; exit 1; }
[ -f "$BUNDLE/session.v4.jsonl" ] || { echo "✗ 缺 session.v4.jsonl"; exit 1; }
[ -f "$BUNDLE/session.meta.json" ] || { echo "✗ 缺 session.meta.json"; exit 1; }

run() { if [ "${DRY_RUN:-0}" = "1" ]; then echo "  [dry] $*"; else "$@"; fi; }

# --- 1. 保证有 zstandard（压缩回 session.v4.jsonl.zstd 要用）---
PY=""
for c in "$VENV/bin/python" python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import zstandard" 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  BASE=$(command -v python3.11 || command -v python3)
  command -v "$BASE" >/dev/null 2>&1 || { echo "✗ 找不到 python3（需要 >=3.8）"; exit 1; }
  echo "== 准备工具环境（首次会装 zstandard）=="
  run "$BASE" -m venv "$VENV"
  run "$VENV/bin/pip" install --quiet --upgrade pip
  run "$VENV/bin/pip" install --quiet zstandard
  PY="$VENV/bin/python"
fi
echo "  工具环境: $PY"

# --- 2. 从 manifest 推出原 DSH_HOME，并算出新 cwd ---
# 注意：macOS 自带 bash 3.2 没有 mapfile，这里用 sed 逐行取（脚本要能在 3.2 上跑）
INFO_RAW="$("$PY" - "$BUNDLE/manifest.json" "$DSH_HOME" <<'PYEOF'
import json, sys, os
m = json.load(open(sys.argv[1], encoding="utf-8"))
new_home = sys.argv[2].rstrip("/")
old_cwd = (m.get("cwd") or "").rstrip("/")
# 原 cwd 形如 <OLD_DSH_HOME>/workdsh-projects/<id>
parts = old_cwd.split("/workdsh-projects/")
if len(parts) != 2:
    print("ERR|manifest 里的 cwd 不含 /workdsh-projects/，无法推断原 DSH_HOME"); sys.exit(1)
old_home, pid = parts
new_cwd = f"{new_home}/workdsh-projects/{pid}"
print(old_home)
print(new_cwd)
print(pid)
PYEOF
)"
OLD_HOME="$(printf '%s\n' "$INFO_RAW" | sed -n '1p')"
NEW_CWD="$(printf '%s\n' "$INFO_RAW" | sed -n '2p')"
PID="$(printf '%s\n' "$INFO_RAW" | sed -n '3p')"
case "$OLD_HOME" in
  ERR*) echo "✗ 推断失败: ${NEW_CWD:-未知}"; exit 1 ;;
esac
[ -n "$OLD_HOME" ] && [ -n "$NEW_CWD" ] || { echo "✗ 无法从 manifest 推断原 DSH_HOME（cwd 里没有 /workdsh-projects/）"; exit 1; }

SID="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['sessionId'])" "$BUNDLE/manifest.json")"
TITLE="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get('title',''))" "$BUNDLE/manifest.json")"

# 目录名编码：cwd 里的 / 换成 -，两侧加 --
ENC="--$(echo "$NEW_CWD" | sed 's#/#-#g')--"
DEST="$DSH_HOME/sessions/$ENC/session-$SID"

echo "== 导入会话 $SID =="
echo "  标题      : $TITLE"
echo "  原 DSH_HOME: $OLD_HOME"
echo "  本机 DSH_HOME: $DSH_HOME"
echo "  新 cwd    : $NEW_CWD"
echo "  正文落点  : $DEST"

# --- 3. 改写路径 + 压缩正文 ---
run mkdir -p "$DEST"
run mkdir -p "$DSH_HOME/storages/session_projcache/sessions"
run mkdir -p "$NEW_CWD"

"$PY" - "$BUNDLE" "$DEST" "$DSH_HOME/storages/session_projcache/sessions" "$OLD_HOME" "$DSH_HOME" "$SID" "${DRY_RUN:-0}" <<'PYEOF'
import json, os, re, sys, zstandard
bundle, dest, projcache, old_home, new_home, sid, dry = sys.argv[1:8]
dry = dry == "1"
op = lambda s: s.replace(old_home, new_home) if old_home and old_home != new_home else s

# 正文：逐行改写（JSONL，逐行处理避免整文件载入）
src = os.path.join(bundle, "session.v4.jsonl")
raw = open(src, encoding="utf-8", errors="replace").read()
raw2 = op(raw)
if dry:
    print(f"  [dry] 正文改写: {len(raw)} -> {len(raw2)} 字节, 替换 {raw.count(old_home)} 处")
else:
    c = zstandard.ZstdCompressor(level=3)
    with open(os.path.join(dest, "session.v4.jsonl.zstd"), "wb") as f:
        f.write(c.compress(raw2.encode("utf-8")))
    open(os.path.join(dest, "session.lock"), "w").close()
    print(f"  正文已写入（{os.path.getsize(os.path.join(dest,'session.v4.jsonl.zstd'))/1048576:.1f} MB 压缩后）")

# 元数据
meta = open(os.path.join(bundle, "session.meta.json"), encoding="utf-8").read()
meta2 = op(meta)
try:
    json.loads(meta2)
    ok = "JSON 校验通过"
except Exception as e:
    ok = f"⚠ JSON 校验失败: {e}"
if dry:
    print(f"  [dry] 元数据改写: 替换 {meta.count(old_home)} 处; {ok}")
else:
    open(os.path.join(projcache, f"session-{sid}.json"), "w", encoding="utf-8").write(meta2)
    print(f"  元数据已写入; {ok}")
PYEOF

# --- 4. 还原产出的文档 ---
if [ -d "$BUNDLE/files" ] && [ -n "$(ls -A "$BUNDLE/files" 2>/dev/null)" ]; then
  echo "== 还原文档 =="
  for f in "$BUNDLE/files"/*; do
    [ -e "$f" ] || continue
    run cp -R "$f" "$NEW_CWD/"
    echo "  $(basename "$f")"
  done
  echo "  已放入 $NEW_CWD"
else
  echo "== 该 bundle 未含文档 =="
fi

cat <<EOF

== 导入完成 ==
  重启服务后即可在会话列表看到：launchctl kickstart -k gui/\$(id -u)/com.workdsh.preview
  若重启后仍不见，检查：
    1) 会话是否属于别的工作区/项目（本脚本按 manifest 恢复 cwd，项目 id 保持不变）
    2) 元数据是否写入成功（storages/session_projcache/sessions/session-${SID}.json）
EOF
