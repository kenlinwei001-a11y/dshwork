# -*- coding: utf-8 -*-
"""Fetch bounded structured observations with citable source URLs.

Supported public sources:
  * FRED   (St. Louis Fed) — macro time series via no-key fredgraph.csv
  * EDGAR  (SEC)           — US filings via data.sec.gov (UA header, no key)
  * Comtrade (UN)          — trade by HS code (public preview; graceful fallback if key-gated)

Each successful result carries a source URL and observation date. Failures return
an explicit ``UNAVAILABLE`` result rather than fabricated data.
"""
import os, sys, io, csv, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from utils import clean_proxy_env
except Exception:
    def clean_proxy_env(): pass

UA = "Resanity research (+https://github.com/Thhoho/reSanity)"


def _get(url, headers=None, timeout=12):
    clean_proxy_env()
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _evidence(claim, number, source, url, date):
    return {"claim": claim, "number": str(number), "source": source, "url": url, "date": str(date)}


# ── FRED: macro series, no key ────────────────────────────────────────────────
def fred_series(series_id):
    """Latest observation of a FRED series (e.g. DGS10, VIXCLS, DTWEXBGS, T10Y2Y)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}"
    try:
        rows = list(csv.reader(io.StringIO(_get(url))))
        last = None
        for row in rows[1:]:
            if len(row) >= 2 and row[1] not in ("", ".", "NaN"):
                last = row
        if not last:
            return {"status": "UNAVAILABLE", "series": series_id, "url": url}
        return {"status": "OK", "series": series_id, "value": float(last[1]), "date": last[0],
                "citation": _evidence(f"FRED {series_id}", last[1], "FRED/StLouisFed", url, last[0])}
    except Exception as e:
        return {"status": "UNAVAILABLE", "series": series_id, "reason": str(e), "url": url}


# ── SEC EDGAR: filings, no key (UA required) ──────────────────────────────────
_TICKERMAP = None
def _cik_for(ticker):
    global _TICKERMAP
    if _TICKERMAP is None:
        data = json.loads(_get("https://www.sec.gov/files/company_tickers.json"))
        _TICKERMAP = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
    return _TICKERMAP.get(ticker.upper())


def edgar_filings(ticker, form="", n=5):
    """Recent SEC filings for a US ticker (optionally filter by form, e.g. 10-K, 8-K)."""
    try:
        cik = _cik_for(ticker)
        if not cik:
            return {"status": "UNAVAILABLE", "ticker": ticker, "reason": "CIK not found"}
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        recent = json.loads(_get(url)).get("filings", {}).get("recent", {})
        forms, dates = recent.get("form", []), recent.get("filingDate", [])
        accns, docs = recent.get("accessionNumber", []), recent.get("primaryDocument", [])
        out = []
        for i in range(len(forms)):
            if form and forms[i] != form:
                continue
            acc = accns[i].replace("-", "")
            out.append({"form": forms[i], "date": dates[i],
                        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{docs[i]}"})
            if len(out) >= n:
                break
        return {"status": "OK", "ticker": ticker, "cik": cik, "filings": out,
                "citation": _evidence(f"SEC EDGAR {ticker} {form or 'filings'}", f"{len(out)} docs",
                                      "SEC EDGAR", url, out[0]["date"] if out else "")}
    except Exception as e:
        return {"status": "UNAVAILABLE", "ticker": ticker, "reason": str(e)}


# ── UN Comtrade: trade by HS code (public preview; key-gated -> graceful fallback) ──
def comtrade_export(reporter_code, partner_code, hs_code, period):
    """Annual export value by HS code. reporter/partner are UN M49 codes (China=156, World=0)."""
    url = (f"https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode={reporter_code}"
           f"&period={period}&partnerCode={partner_code}&cmdCode={hs_code}&flowCode=X")
    try:
        rows = json.loads(_get(url)).get("data", [])
        if not rows:
            return {"status": "UNAVAILABLE", "url": url,
                    "note": "无数据或需注册key；海关/出口数据可用 WebSearch 兜底(Tier-2)。"}
        v = rows[0].get("primaryValue")
        return {"status": "OK", "value": v, "url": url,
                "citation": _evidence(f"Comtrade HS{hs_code} {reporter_code}->{partner_code} export {period}",
                                      v, "UN Comtrade", url, period)}
    except Exception as e:
        return {"status": "UNAVAILABLE", "url": url, "reason": str(e),
                "note": "UN Comtrade 新API通常需注册key；无key时用 WebSearch 兜底海关数据(Tier-2)。"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Resanity structured data providers")
    ap.add_argument("--fred", help="FRED series id, e.g. DGS10")
    ap.add_argument("--edgar", help="US ticker, e.g. NVDA"); ap.add_argument("--form", default="")
    ap.add_argument("--comtrade", nargs=4, metavar=("REPORTER", "PARTNER", "HS", "PERIOD"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        print("FRED DGS10 (US 10Y):", json.dumps(fred_series("DGS10"), ensure_ascii=False))
        e = edgar_filings("NVDA", form="10-K", n=2)
        print("EDGAR NVDA 10-K:", json.dumps({k: e[k] for k in ("status", "cik", "citation") if k in e}, ensure_ascii=False))
        print("Comtrade China solar(854143)->World 2023:",
              json.dumps(comtrade_export(156, 0, "854143", 2023).get("status"), ensure_ascii=False))
    elif a.fred:
        print(json.dumps(fred_series(a.fred), ensure_ascii=False, indent=2))
    elif a.edgar:
        print(json.dumps(edgar_filings(a.edgar, form=a.form), ensure_ascii=False, indent=2))
    elif a.comtrade:
        r, p, hs, per = a.comtrade
        print(json.dumps(comtrade_export(int(r), int(p), hs, per), ensure_ascii=False, indent=2))
