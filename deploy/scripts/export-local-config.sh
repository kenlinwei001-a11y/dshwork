#!/usr/bin/env bash
# 把本机当前状态导出成 deploy/config 存档（install-local-config.sh 的逆操作）。
# 用法：
#   bash deploy/scripts/export-local-config.sh                 # 导出
#   bash deploy/scripts/export-local-config.sh --check         # 只比对（0=一致 1=有差异）
#   bash deploy/scripts/export-local-config.sh --dry-run
#   bash deploy/scripts/export-local-config.sh <DSH_HOME> <DSH_AGENTS_HOME>
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$HERE/config"
MODE="export"
POS=""
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --dry-run) MODE="dry" ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    -*) echo "未知参数：$a"; exit 2 ;;
    *) POS="$POS $a" ;;
  esac
done
set -- $POS
if [ $# -ge 1 ]; then DSH_HOME="$1"; else DSH_HOME="$HOME/.workdsh/preview"; fi
if [ $# -ge 2 ]; then AGENTS_HOME="$2"; else AGENTS_HOME="$HOME/.agents"; fi
[ -d "$DSH_HOME" ] || { echo "找不到 DSH_HOME：$DSH_HOME"; exit 2; }
[ -d "$AGENTS_HOME" ] || { echo "找不到 DSH_AGENTS_HOME：$AGENTS_HOME"; exit 2; }

say() { echo "  $*"; }
step() { echo; echo "── $* ──"; }
do_cp() { if [ "$MODE" = "export" ]; then cp -R "$1" "$2"; else echo "  [dry] cp -R $1 $2"; fi; }

echo "== 源 =="
say "DSH_HOME        : $DSH_HOME"
say "DSH_AGENTS_HOME : $AGENTS_HOME"
say "存档目录        : $SRC"
say "模式            : $MODE"
CHANGED=0

step "1/4 专家（experts / preferences / revisions）"
mkdir -p "$SRC/experts"
for sub in experts preferences revisions; do
  src_dir="$DSH_HOME/storages/workdsh_experts/$sub"
  if [ ! -d "$src_dir" ]; then say "跳过 $sub（不存在）"; continue; fi
  if [ "$MODE" = "check" ]; then
    new_n=$(ls -1 "$src_dir" | wc -l | tr -d ' ')
    old_n=0
    if [ -d "$SRC/experts/$sub" ]; then old_n=$(ls -1 "$SRC/experts/$sub" | wc -l | tr -d ' '); fi
    if [ "$new_n" != "$old_n" ]; then say "$sub 数量不同：存档 $old_n / 本机 $new_n"; CHANGED=1; fi
  else
    if [ "$MODE" = "export" ]; then rm -rf "$SRC/experts/$sub"; fi
    do_cp "$src_dir" "$SRC/experts/$sub"
    say "$sub: $(ls -1 "$src_dir" | wc -l | tr -d ' ') 个文件"
  fi
done

step "2/4 Agent 预设（只导已发布修订引用的）"
# 预设有两个真实位置：系统读取的 DSH_HOME/.agent-presets，以及 agents 侧的编译产物目录
PRESET_SRC_A="$DSH_HOME/.agent-presets"
PRESET_SRC_B="$AGENTS_HOME/.workdsh-state/experts/presets"
map_out="$(node -e '
const fs=require("fs"), path=require("path");
const ex=process.argv[1], rv=process.argv[2];
const out=[];
if (fs.existsSync(ex)) {
  for (const f of fs.readdirSync(ex)) {
    if (!f.endsWith(".json")) continue;
    let rec; try { rec=JSON.parse(fs.readFileSync(path.join(ex,f),"utf8")).record; } catch (e) { continue; }
    const pr=rec.publishedRevisionRef;
    if (!pr || !pr.revisionId) continue;
    const rf=path.join(rv, rec.id + "_" + pr.revisionId + ".json");
    if (!fs.existsSync(rf)) continue;
    let r; try { r=JSON.parse(fs.readFileSync(rf,"utf8")).record; } catch (e) { continue; }
    const pid=r.presetRevisionRef;
    if (!pid) continue;
    out.push(rec.id + "|" + pid);
  }
}
process.stdout.write(out.join("\n"));
' "$DSH_HOME/storages/workdsh_experts/experts" "$DSH_HOME/storages/workdsh_experts/revisions")"

if [ -z "$map_out" ]; then
  say "没有找到带预设的已发布修订"
else
  if [ "$MODE" = "export" ]; then rm -rf "$SRC/agent-presets"; fi
  mkdir -p "$SRC/agent-presets"
  n=0; miss=0
  printf '%s\n' "$map_out" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    eid=$(printf '%s' "$line" | cut -d'|' -f1)
    pid=$(printf '%s' "$line" | cut -d'|' -f2)
    src_dir=""
    if [ -n "$pid" ]; then
      if [ -d "$PRESET_SRC_A/$pid" ]; then src_dir="$PRESET_SRC_A/$pid"; fi
      if [ -z "$src_dir" ] && [ -d "$PRESET_SRC_B/$pid" ]; then src_dir="$PRESET_SRC_B/$pid"; fi
    fi
    if [ -n "$src_dir" ]; then
      if [ "$MODE" = "check" ]; then
        if [ ! -d "$SRC/agent-presets/$pid" ]; then say "缺预设：$pid（专家 $eid）"; CHANGED=1; fi
      else
        do_cp "$src_dir" "$SRC/agent-presets/$pid"
      fi
    elif [ -n "$pid" ]; then
      say "预设目录不存在，跳过：$pid（专家 $eid）"
    fi
  done
  say "预设处理完成（目录：$SRC/agent-presets）"
fi

step "3/4 技能（用户根 -> skills，Profile 根 -> skills-profile）"
copy_skills() {
  from_dir="$1"; to_dir="$2"; label="$3"
  if [ ! -d "$from_dir" ]; then say "跳过 $label（不存在）"; return 0; fi
  if [ "$MODE" = "check" ]; then
    new_n=$(ls -1 "$from_dir" | wc -l | tr -d ' ')
    old_n=0
    if [ -d "$to_dir" ]; then old_n=$(ls -1 "$to_dir" | wc -l | tr -d ' '); fi
    if [ "$new_n" != "$old_n" ]; then say "$label 数量不同：存档 $old_n / 本机 $new_n"; CHANGED=1; fi
    return 0
  fi
  if [ "$MODE" = "export" ]; then rm -rf "$to_dir"; fi
  mkdir -p "$to_dir"
  for d in "$from_dir"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    case "$name" in .*|__*) continue ;; esac
    do_cp "$d" "$to_dir/$name"
    if [ "$MODE" = "export" ]; then
      rm -f "$to_dir/$name/.DS_Store" 2>/dev/null || true
      rm -f "$to_dir/$name"/SKILL.md.bak* 2>/dev/null || true
    fi
  done
  say "$label：$(ls -1 "$to_dir" | wc -l | tr -d ' ') 个技能"
}
copy_skills "$AGENTS_HOME/skills" "$SRC/skills" "用户根技能"
copy_skills "$DSH_HOME/skills" "$SRC/skills-profile" "Profile 根技能"

step "4/4 MCP 连接器定义"
SRCD="$DSH_HOME/storages/workdsh_connectors/definitions"
if [ -d "$SRCD" ]; then
  if [ "$MODE" = "check" ]; then
    new_n=$(ls -1 "$SRCD"/*.json 2>/dev/null | wc -l | tr -d ' ')
    old_n=$(ls -1 "$SRC/mcp-connectors"/*.json 2>/dev/null | wc -l | tr -d ' ')
    if [ "$new_n" != "$old_n" ]; then say "连接器数量不同：存档 $old_n / 本机 $new_n"; CHANGED=1; fi
  else
    if [ "$MODE" = "export" ]; then rm -rf "$SRC/mcp-connectors"; fi
    mkdir -p "$SRC/mcp-connectors"
    for f in "$SRCD"/*.json; do
      [ -f "$f" ] || continue
      b="$(basename "$f")"
      if [ "$b" = "global.json" ]; then continue; fi
      do_cp "$f" "$SRC/mcp-connectors/$b"
    done
    say "连接器：$(ls -1 "$SRC/mcp-connectors"/*.json 2>/dev/null | wc -l | tr -d ' ') 条"
  fi
else
  say "跳过（没有 definitions 目录）"
fi

step "结果"
if [ "$MODE" = "check" ]; then
  if [ "$CHANGED" = "0" ]; then echo "存档与当前机器一致"; exit 0; else echo "存档已过期（见上面的差异）"; exit 1; fi
fi
echo "存档已更新：$SRC"
echo "下一步：git add deploy/config && git commit -m 'chore(deploy): 刷新存档'"
echo "注意：mcp-connectors-dsh（dsh 侧注册表）不导出——里面有 token，需要对方自己添加并授权。"
