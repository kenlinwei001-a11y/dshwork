#!/usr/bin/env python3
"""按时间归档 WorkDSH 审计事件。

默认：保留最近 30 天在 live 目录，超过 30 天的事件按月份打包到归档目录，
验证 tar 内容后才从 live 删除。只读失败/无法解析时间的文件会保留，不会删除。

用法：
  python3 deploy/scripts/archive-audit-events.py --dry-run
  python3 deploy/scripts/archive-audit-events.py --apply
  python3 deploy/scripts/archive-audit-events.py --apply --keep-days 14 \
      --archive-dir "$HOME/Desktop/workdsh-audit-archive"

恢复某个月的归档：
  tar -xzf <archive-dir>/workdsh-audit-2026-09-*.tar.gz \
      -C <DSH_HOME>/storages/workdsh_audit/events
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import tarfile

DEFAULT_HOME = os.path.expanduser("~/workdsh/.test-runtime/preview")
DEFAULT_ARCHIVE = os.path.expanduser("~/Desktop/workdsh-audit-archive")


def parse_time(value):
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", default=os.environ.get("DSH_HOME") or DEFAULT_HOME)
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="只预览；未加 --apply 时默认就是 dry-run")
    parser.add_argument("--apply", action="store_true", help="实际归档并删除 live 文件；默认只预览")
    args = parser.parse_args()

    events_dir = os.path.join(args.home, "storages", "workdsh_audit", "events")
    if not os.path.isdir(events_dir):
        print("找不到审计事件目录: %s" % events_dir)
        return 2
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=args.keep_days)
    groups = {}
    kept = 0
    unreadable = 0
    total = 0
    for name in os.listdir(events_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(events_dir, name)
        if not os.path.isfile(path):
            continue
        total += 1
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle).get("record", {})
            occurred = parse_time(record.get("occurredAt"))
        except Exception:
            unreadable += 1
            continue
        if occurred >= cutoff:
            kept += 1
            continue
        groups.setdefault(occurred.strftime("%Y-%m"), []).append(path)

    print("events=%d keep=%d archive=%d unreadable_keep=%d keep_days=%d" % (
        total, kept, sum(len(v) for v in groups.values()), unreadable, args.keep_days))
    for month in sorted(groups):
        print("  %s: %d files" % (month, len(groups[month])))
    if not args.apply:
        print("dry-run：未写归档、未删除 live 文件")
        return 0
    if not groups:
        print("没有需要归档的事件")
        return 0

    os.makedirs(args.archive_dir, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    manifest = {
        "generatedAt": now.isoformat(),
        "keepDays": args.keep_days,
        "cutoff": cutoff.isoformat(),
        "months": {},
    }
    failed = 0
    for month in sorted(groups):
        files = sorted(groups[month])
        archive_path = os.path.join(
            args.archive_dir, "workdsh-audit-%s-%s.tar.gz" % (month, stamp))
        added = removed = 0
        try:
            with tarfile.open(archive_path, "w:gz") as archive:
                for path in files:
                    if not os.path.isfile(path):
                        continue
                    archive.add(path, arcname=os.path.basename(path))
                    added += 1
            with tarfile.open(archive_path, "r:gz") as archive:
                members = [member for member in archive.getmembers() if member.isfile()]
            if len(members) != added:
                raise RuntimeError("tar verification count %d != %d" % (len(members), added))
            for path in files:
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            manifest["months"][month] = {
                "archive": os.path.basename(archive_path),
                "files": added,
                "removed": removed,
                "bytes": os.path.getsize(archive_path),
                "sha256": sha256_file(archive_path),
            }
            print("  archived %s: %d files -> %s" % (month, added, archive_path))
        except Exception as error:
            failed += 1
            print("  ERROR %s: %s（已保留 live 文件）" % (month, error))

    manifest_path = os.path.join(args.archive_dir, "MANIFEST-%s.json" % stamp)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print("manifest: %s" % manifest_path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
