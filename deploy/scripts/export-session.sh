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

# 5) 强制脱敏 + 复扫。
#    教训：本仓是 public，GitHub 有 push protection——含密钥的推送会被直接 reject。
#    而且"我扫过了"不作数：只扫一部分、或只信自己的模式，都会漏。
#    所以这里做成必跑的一步：先替换，再复扫，命中非 0 就报错退出。
echo "== 脱敏与复扫 =="
"$PY" - "$OUT" <<'PYEOF'
import re, os, sys
out = sys.argv[1]
RULES = [
    (re.compile(r'sk-[A-Za-z0-9_\-]{20,}'), 'sk-<REDACTED-LLM-API-KEY>'),
    (re.compile(r'ghp_[A-Za-z0-9]{20,}'), 'ghp_<REDACTED-GITHUB-PAT>'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{20,}'), 'github_pat_<REDACTED-GITHUB-PAT>'),
    (re.compile(r'(?<=token=)[A-Za-z0-9_\-]{16,}'), '<REDACTED-SESSION-TOKEN>'),
    (re.compile(r'((?:DEEPSEEK|MOONSHOT|OPENAI|ANTHROPIC)_API_KEY["\']?\s*[:=]\s*["\']?)([A-Za-z0-9_\-]{16,})'),
     r'\1<REDACTED-API-KEY>'),
]
for name in ("session.v4.jsonl", "session.meta.json", "manifest.json"):
    p = os.path.join(out, name)
    if not os.path.isfile(p):
        continue
    s = open(p, encoding="utf-8", errors="replace").read()
    tot = 0
    for pat, repl in RULES:
        s, n = pat.subn(repl, s)
        tot += n
    open(p, "w", encoding="utf-8").write(s)
    print(f"  {name}: 脱敏 {tot} 处")

# 复扫：正文 + 元数据 + files/ 里的文本文件
CHECK = [re.compile(r'sk-[A-Za-z0-9_\-]{20,}'), re.compile(r'ghp_[A-Za-z0-9]{20,}'),
         re.compile(r'token=[A-Za-z0-9_\-]{16,}')]
# 活性对照：同样用正则去匹配一个**必然存在**的东西（"type" 在会话 JSONL 里必现）。
# 若连它都 0 命中，说明扫描本身瞎了（读不到内容 / 模式机制失效），此时"密钥残留 0"毫无意义。
ALIVE = re.compile(r'"type"\s*:')
bad = []
scanned = read_bytes = alive_hits = 0
for root, _, fs in os.walk(out):
    for f in fs:
        p = os.path.join(root, f)
        try:
            if os.path.getsize(p) > 200 * 1024 * 1024:
                continue
            t = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        scanned += 1
        read_bytes += len(t)
        alive_hits += len(ALIVE.findall(t))
        for c in CHECK:
            if c.search(t):
                bad.append(os.path.relpath(p, out)); break
print(f"  扫描覆盖: {scanned} 个文件 / {read_bytes/1048576:.1f} MB / 活性对照命中 {alive_hits} 处")
if alive_hits == 0:
    print("  ✗ 活性对照 0 命中 —— 扫描没读到内容，本次'残留 0'不作数，判废")
    sys.exit(3)
if bad:
    print("  ✗ 复扫仍命中（这些文件含密钥，禁止推送）:")
    for b in sorted(set(bad)):
        print("     -", b)
    sys.exit(2)
print("  ✓ 复扫通过：真密钥残留 0（且活性对照非 0，证明扫描确实在跑）")
PYEOF
SCAN_RC=$?
if [ "$SCAN_RC" != "0" ]; then
  echo "✗ 导出中止：复扫未通过，先处理上面的文件再推（files/ 里的二进制若确实含密钥，请勿入库）"
  exit 1
fi

echo
echo "== 导出完成 =="
du -sh "$OUT" | sed 's/^/  体积: /'
echo "  下一步: git add '$OUT' && git commit && git push"
echo "  对方:   bash deploy/scripts/import-session.sh '$OUT'"
