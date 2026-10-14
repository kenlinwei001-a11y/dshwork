#!/usr/bin/env bash
# 把本机的一条会话（含它产出的文档）导出成可搬移的 bundle，供他人 import-session.sh 导入。
#
# 用法：
#   bash deploy/scripts/export-session.sh <session-id> [输出目录] [--files <项目顶层条目>...]
# 例：
#   bash deploy/scripts/export-session.sh 9b496023dca67e6b220f7130478cca37 \
#        会话记录/可研报告处理为资产域并打包 --files 上财大数据研究中心可研-资产域包-v1.zip 交付物
# 环境变量：
#   WORKDSH_HOME  目标部署的 home，默认 $HOME/workdsh/.test-runtime/preview
#                （注意：不读环境里的 DSH_HOME——本机它指向桌面版 Harness，读它会导致找错地方）
set -euo pipefail

SID="${1:-}"; OUT="${2:-}"; shift 2 2>/dev/null || true
FILES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --files) shift; while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do FILES+=("$1"); shift; done ;;
    *) shift ;;
  esac
done

WORKDSH_HOME="${WORKDSH_HOME:-$HOME/workdsh/.test-runtime/preview}"
DSH_HOME="$WORKDSH_HOME"
[ -n "$SID" ] || { echo "✗ 用法: export-session.sh <session-id> [输出目录] [--files 条目...]"; exit 1; }
[ -d "$DSH_HOME" ] || { echo "✗ DSH_HOME 不存在: $DSH_HOME"; exit 1; }
OUT="${OUT:-会话记录/session-$SID}"

PY=""
for c in "$HOME/.venvs/semantica/bin/python" python3.11 python3; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -n "$PY" ] || { echo "✗ 找不到 python"; exit 1; }

SESS_DIR="$(find "$DSH_HOME/sessions" -maxdepth 2 -type d -name "session-$SID" 2>/dev/null | head -1)"
[ -n "$SESS_DIR" ] || { echo "✗ 找不到会话目录 session-$SID"; exit 1; }
META="$DSH_HOME/storages/session_projcache/sessions/session-$SID.json"
[ -f "$META" ] || { echo "✗ 找不到会话元数据: $META"; exit 1; }

mkdir -p "$OUT/files"
echo "== 导出会话 $SID =="
echo "  来源: $SESS_DIR"

# 1) 正文：zstd -> 明文 JSONL（便于查看，导入时再压回去）
"$PY" - "$SESS_DIR/session.v4.jsonl.zstd" "$OUT/session.v4.jsonl" <<'PYEOF'
import sys, zstandard
src, dst = sys.argv[1], sys.argv[2]
d = zstandard.ZstdDecompressor()
with open(src, "rb") as f, open(dst, "wb") as o:
    d.copy_stream(f, o)
print("  正文已解压 ->", dst)
PYEOF

# 2) 元数据
cp "$META" "$OUT/session.meta.json"
echo "  元数据已复制（$(du -h "$OUT/session.meta.json" | cut -f1)）"

# 3) 清单
"$PY" - "$OUT/manifest.json" "$SID" "$META" "$SESS_DIR" "${FILES[@]:-}" <<'PYEOF'
import json, sys, os
out, sid, meta, sessdir = sys.argv[1:5]
files = [a for a in sys.argv[5:] if a]
m = json.load(open(meta, encoding="utf-8"))
ident = m["record"]["identity"]
title = (m["record"]["rows"].get("title") or {}).get("val", "")
json.dump({
    "schema": 1,
    "sessionId": sid,
    "title": title,
    "cwd": ident.get("cwd"),
    "sourceSessionsDir": sessdir,
    "exportedBy": os.environ.get("USER", ""),
    "files": files,
}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("  标题:", title)
PYEOF

# 4) 产出的文档（从会话的 cwd 里挑）
if [ "${#FILES[@]}" -gt 0 ]; then
  PROJ="$(/usr/local/bin/python3.11 -c "import json,sys;print(json.load(open('$OUT/manifest.json',encoding='utf-8'))['cwd'] or '')" 2>/dev/null || echo "")"
  for f in "${FILES[@]}"; do
    src="$PROJ/$f"
    if [ -e "$src" ]; then
      cp -R "$src" "$OUT/files/"
      echo "  文档: ${f}（$(du -sh "$OUT/files/$(basename "$f")" 2>/dev/null | cut -f1)）"
    else
      echo "  ⚠ 找不到: $src"
    fi
  done
else
  echo "  （未指定 --files，只导出会话本身）"
fi

echo
echo "== 导出完成 =="
du -sh "$OUT" | sed 's/^/  体积: /'
echo "  下一步: git add '$OUT' && git commit && git push"
echo "  对方:   bash deploy/scripts/import-session.sh '$OUT'"
