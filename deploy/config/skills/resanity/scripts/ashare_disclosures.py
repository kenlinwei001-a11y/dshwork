#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enumerate a bounded A-share official-disclosure index from CNINFO.

The command is deliberately narrow: resolve one ticker, find the latest full
periodic report visible by ``--as-of``, then enumerate every announcement from
the earlier of that report date and the 120-day lookback.  It performs no
keyword search and no automatic fallback.  Network/schema failures are emitted
as an explicit JSON ``UNAVAILABLE`` result and a non-zero exit code.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import html
import json
import re
import sys
from typing import Any, Callable
from urllib import parse, request


SCHEMA_VERSION = "resanity.ashare-disclosure-index.v1"
CNINFO = "https://www.cninfo.com.cn"
STATIC_CNINFO = "https://static.cninfo.com.cn/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/138.0 Safari/537.36 Resanity/0.2"
)
PERIODIC_REPORT = re.compile(
    r"(?:19|20)\d{2}\s*年?(?:年度报告|半年度报告|第一季度报告|第三季度报告|一季度报告|三季度报告)(?:全文)?$"
)
TAG = re.compile(r"<[^>]+>")


class DisclosureUnavailable(RuntimeError):
    """The official index could not be enumerated under the declared contract."""


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def infer_market(ticker: str) -> str:
    if ticker.startswith(("0", "3")):
        return "szse"
    if ticker.startswith(("4", "8", "92")):
        return "bj"
    if ticker.startswith(("6", "68")):
        return "sse"
    raise DisclosureUnavailable(f"cannot infer A-share market for ticker {ticker}")


def clean_title(value: Any) -> str:
    return html.unescape(TAG.sub("", value if isinstance(value, str) else "")).strip()


def read_json(
    url: str,
    *,
    data: bytes | None = None,
    timeout: float = 15,
    opener: Callable[..., Any] = request.urlopen,
) -> Any:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{CNINFO}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = request.Request(url, data=data, headers=headers)
    try:
        with opener(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
        return json.loads(raw)
    except Exception as error:
        raise DisclosureUnavailable(f"CNINFO request failed: {error}") from error


def rows_from_search(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("stockList", "data", "result", "records", "list"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def resolve_company(
    ticker: str,
    *,
    timeout: float = 15,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, str]:
    payload = read_json(
        f"{CNINFO}/new/data/szse_stock.json",
        timeout=timeout,
        opener=opener,
    )
    matches = []
    for row in rows_from_search(payload):
        code = str(row.get("code") or row.get("secCode") or "").strip()
        org_id = str(row.get("orgId") or row.get("orgid") or "").strip()
        if code == ticker and org_id:
            matches.append(
                {
                    "ticker": ticker,
                    "company": str(
                        row.get("zwjc")
                        or row.get("secName")
                        or row.get("value")
                        or ""
                    ).strip(),
                    "org_id": org_id,
                    "market": infer_market(ticker),
                }
            )
    unique = {(row["ticker"], row["org_id"]): row for row in matches}
    if len(unique) != 1:
        raise DisclosureUnavailable(
            f"CNINFO company resolution expected one exact match, got {len(unique)}"
        )
    return next(iter(unique.values()))


def announcement_date(row: dict[str, Any]) -> date | None:
    value = row.get("announcementTime") or row.get("announcementDate")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(
                value / 1000, tz=timezone(timedelta(hours=8))
            ).date()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        match = re.search(r"(?:19|20)\d{2}-\d{2}-\d{2}", value)
        if match:
            return date.fromisoformat(match.group(0))
    return None


def classify_title(title: str) -> str:
    if PERIODIC_REPORT.search(title) and "摘要" not in title:
        return "periodic_report"
    rules = (
        ("financing", ("融资", "募集资金", "发行股票", "可转债", "授信")),
        ("guarantee", ("担保",)),
        ("litigation", ("诉讼", "仲裁")),
        ("repurchase", ("回购",)),
        ("control_governance", ("控制权", "实际控制人", "董事", "监事", "高级管理人员", "治理")),
        ("pledge_restriction", ("质押", "限售", "解除限售", "冻结")),
    )
    for category, keywords in rules:
        if any(keyword in title for keyword in keywords):
            return category
    return "other"


def normalize_announcement(row: dict[str, Any]) -> dict[str, Any] | None:
    published = announcement_date(row)
    title = clean_title(row.get("announcementTitle") or row.get("title"))
    announcement_id = str(row.get("announcementId") or row.get("id") or "").strip()
    adjunct = str(row.get("adjunctUrl") or "").lstrip("/")
    if published is None or not title or not announcement_id:
        return None
    return {
        "announcement_id": announcement_id,
        "published_date": published.isoformat(),
        "title": title,
        "category": classify_title(title),
        "url": parse.urljoin(STATIC_CNINFO, adjunct) if adjunct else None,
    }


def query_announcements(
    company: dict[str, str],
    start: date,
    end: date,
    *,
    page_size: int = 30,
    max_pages: int = 100,
    stop_at_first_periodic: bool = False,
    timeout: float = 15,
    opener: Callable[..., Any] = request.urlopen,
) -> tuple[list[dict[str, Any]], bool]:
    endpoint = f"{CNINFO}/new/hisAnnouncement/query"
    rows: list[dict[str, Any]] = []
    complete = False
    for page in range(1, max_pages + 1):
        form = {
            "pageNum": page,
            "pageSize": page_size,
            "column": company["market"],
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{company['ticker']},{company['org_id']}",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start.isoformat()}~{end.isoformat()}",
            "sortName": "time",
            "sortType": "desc",
            "isHLtitle": "true",
        }
        payload = read_json(
            endpoint,
            data=parse.urlencode(form).encode("utf-8"),
            timeout=timeout,
            opener=opener,
        )
        page_rows = payload.get("announcements") if isinstance(payload, dict) else None
        if not isinstance(page_rows, list):
            raise DisclosureUnavailable("CNINFO announcement response schema changed")
        normalized = [normalize_announcement(row) for row in page_rows if isinstance(row, dict)]
        rows.extend(row for row in normalized if row is not None)
        if stop_at_first_periodic and any(
            row["category"] == "periodic_report" for row in rows
        ):
            return rows, False
        has_more = payload.get("hasMore") if isinstance(payload, dict) else None
        total = payload.get("totalAnnouncement") if isinstance(payload, dict) else None
        if has_more is False or not page_rows or (
            isinstance(total, int) and page * page_size >= total
        ):
            complete = True
            break
    return rows, complete


def build_index(
    ticker: str,
    as_of: date,
    *,
    market: str | None = None,
    date_from: date | None = None,
    lookback_days: int = 120,
    page_size: int = 30,
    timeout: float = 15,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    company = resolve_company(ticker, timeout=timeout, opener=opener)
    resolved_market = company.get("market")
    inferred_market = (
        market
        or (resolved_market if resolved_market in {"szse", "sse", "bj"} else None)
        or infer_market(ticker)
    )
    company["market"] = inferred_market

    latest_periodic = None
    if date_from is None:
        discovery_from = as_of - timedelta(days=550)
        discovery, _ = query_announcements(
            company,
            discovery_from,
            as_of,
            page_size=page_size,
            max_pages=20,
            stop_at_first_periodic=True,
            timeout=timeout,
            opener=opener,
        )
        periodic = [
            row for row in discovery if row["category"] == "periodic_report"
        ]
        if not periodic:
            raise DisclosureUnavailable(
                "latest full periodic report not found in bounded CNINFO discovery window"
            )
        latest_periodic = max(periodic, key=lambda row: row["published_date"])
        coverage_from = min(
            as_of - timedelta(days=lookback_days),
            date.fromisoformat(latest_periodic["published_date"]),
        )
    else:
        coverage_from = date_from

    announcements, complete = query_announcements(
        company,
        coverage_from,
        as_of,
        page_size=page_size,
        timeout=timeout,
        opener=opener,
    )
    if not complete:
        raise DisclosureUnavailable("CNINFO index exceeded the bounded 100-page limit")
    deduplicated = {
        row["announcement_id"]: row
        for row in announcements
        if row["published_date"] <= as_of.isoformat()
    }
    ordered = sorted(
        deduplicated.values(),
        key=lambda row: (row["published_date"], row["announcement_id"]),
        reverse=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "OK",
        "source": "CNINFO official disclosure platform",
        "source_url": f"{CNINFO}/new/disclosure/stock?stockCode={ticker}&orgId={company['org_id']}",
        "ticker": ticker,
        "company": company["company"],
        "org_id": company["org_id"],
        "market": inferred_market,
        "as_of": as_of.isoformat(),
        "coverage_from": coverage_from.isoformat(),
        "coverage_through": as_of.isoformat(),
        "latest_periodic_report": latest_periodic,
        "announcement_count": len(ordered),
        "announcements": ordered,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="six-digit A-share ticker")
    parser.add_argument("--as-of", required=True, type=parse_iso_date)
    parser.add_argument("--market", choices=("szse", "sse", "bj"))
    parser.add_argument("--date-from", type=parse_iso_date)
    parser.add_argument("--lookback-days", type=int, default=120)
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{6}", args.ticker):
        parser.error("--ticker must be exactly six digits")
    if args.lookback_days < 1 or not 1 <= args.page_size <= 100 or args.timeout <= 0:
        parser.error("lookback, page size, and timeout must be positive")
    if args.date_from is not None and args.date_from > args.as_of:
        parser.error("--date-from must not be later than --as-of")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = build_index(
            args.ticker,
            args.as_of,
            market=args.market,
            date_from=args.date_from,
            lookback_days=args.lookback_days,
            page_size=args.page_size,
            timeout=args.timeout,
        )
        exit_code = 0
    except DisclosureUnavailable as error:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "UNAVAILABLE",
            "source": "CNINFO official disclosure platform",
            "ticker": args.ticker,
            "as_of": args.as_of.isoformat(),
            "reason": str(error),
        }
        exit_code = 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
