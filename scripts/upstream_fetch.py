"""upstream_fetch.py — Fetch chart data trực tiếp từ HNX/SBV/FRED (portable, không API local).

Port patterns từ Bond Lab providers:
  - HNX yield curve: POST pDate → parse HTML table
  - HNX auction: POST range search → parse HTML table  
  - FRED: JSON API, chunk 90 ngày
  - VN-format number parser (comma decimal, dot thousands)

Output: JSON cho 5 charts (12+ tuần history).
"""
from __future__ import annotations
import json
import os
import re
import ssl
import time
import urllib.request
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# SSL context — Bond Lab uses httpx+certifi/truststore.
# HNX cert chain không có intermediate trong certifi → cần unverified fallback.
# FRED dùng cert chuẩn → verified OK.
SSL_HNX = ssl.create_default_context()
SSL_HNX.check_hostname = False
SSL_HNX.verify_mode = ssl.CERT_NONE

SSL_VERIFIED = ssl.create_default_context()

HNX_BASE = "https://hnx.vn"
HNX_YIELD_URL = f"{HNX_BASE}/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData"
HNX_AUCTION_URL = f"{HNX_BASE}/ModuleReportBonds/Bond_DauThau/Bond_KetQua_DauThau"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Tenor maps (port từ Bond Lab hnx_yield_curve.py:38-50)
YIELD_TENORS = {
    "1 năm": ("1Y", 365), "2 năm": ("2Y", 730), "3 năm": ("3Y", 1095),
    "5 năm": ("5Y", 1825), "7 năm": ("7Y", 2555), "10 năm": ("10Y", 3650),
    "15 năm": ("15Y", 5475), "20 năm": ("20Y", 7300),
}


def parse_vn_float(value: str) -> Optional[float]:
    """Port từ Bond Lab base.py:180 — VN number parser.
    
    Handles: '1.234,56' → 1234.56, '1.234.567' → 1234567, '4,5%' → 4.5
    """
    if not value:
        return None
    s = str(value).strip().rstrip("%").strip()
    if s in ("", "-", "N/A", "NA"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Check if dot = thousands (XXX.XXX format, 3 digits after each dot)
        if re.match(r"^\d{1,3}(\.\d{3})+$", s):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def http_post(url: str, data: dict, headers: dict = None, ctx=SSL_HNX) -> str:
    """HTTP POST returning text."""
    body = urllib.parse.urlencode(data).encode()
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def http_get(url: str, headers: dict = None, ctx=SSL_VERIFIED) -> str:
    """HTTP GET returning text."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_hnx_yield(target_date: date) -> list[dict]:
    """Fetch HNX yield curve for a single date. Port từ Bond Lab hnx_yield_curve.py.
    
    POST pDate=dd/mm/YYYY → parse HTML table#_tableDatas.
    Returns list of {date, tenor, par_yield}.
    """
    pdate = target_date.strftime("%d/%m/%Y")
    try:
        html = http_post(HNX_YIELD_URL, {"pDate": pdate})  # SSL_HNX default
    except Exception:
        return []
    
    if "Không tìm thấy dữ liệu" in html or len(html) < 500:
        return []
    
    rows = []
    
    # Parse table rows — find tbody
    tbody_match = re.search(r'<tbody>(.*?)</tbody>', html, re.DOTALL | re.IGNORECASE)
    if not tbody_match:
        return []
    
    import html as html_mod
    tr_list = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_match.group(1), re.DOTALL | re.IGNORECASE)
    
    for tr in tr_list:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL | re.IGNORECASE)
        if len(tds) < 3:
            continue
        cells = [html_mod.unescape(re.sub(r"<[^>]+>", "", td).strip()) for td in tds]
        
        # Exact match tenor (không substring — "15 năm" không match "5 năm")
        tenor_raw = cells[0].strip()
        matched_label = None
        for vn_tenor, (label, days) in YIELD_TENORS.items():
            if tenor_raw == vn_tenor:
                matched_label = label
                break
        if not matched_label:
            continue
        
        # Bond Lab pattern: cols[2] = par_yield
        yield_val = parse_vn_float(cells[2]) if len(cells) > 2 else None
        if yield_val is None or not (0.1 < yield_val < 15):
            yield_val = parse_vn_float(cells[1]) if len(cells) > 1 else None
        if yield_val and 0.1 < yield_val < 15:
            rows.append({
                "date": target_date.isoformat(),
                "tenor": matched_label,
                "yield": yield_val,
            })
    return rows


def fetch_hnx_yield_range(start: date, end: date, tenors: list[str] = None) -> list[dict]:
    """Backfill HNX yield curve ngày từng ngày (port pattern từ Bond Lab backfill loop)."""
    all_rows = []
    current = start
    while current <= end:
        # Skip weekends (HNX doesn't publish Sat/Sun)
        if current.weekday() < 5:
            rows = fetch_hnx_yield(current)
            if tenors:
                rows = [r for r in rows if r["tenor"] in tenors]
            all_rows.extend(rows)
            time.sleep(0.5)  # Rate limit (Bond Lab uses 1.0s)
        current += timedelta(days=1)
    return all_rows


def fetch_hnx_auction_range(start: date, end: date) -> list[dict]:
    """Fetch HNX auction results for date range. Port từ Bond Lab hnx_auction.py.
    
    POST p_keysearch=from|to|||... → parse HTML table.
    HNX table: 21 cols. Col 5=Kỳ hạn, Col 9=GT gọi thầu, Col 11=GT trúng thầu, Col 18=Lãi suất trúng thầu.
    """
    import html as html_mod
    
    from_str = start.strftime("%d/%m/%Y")
    to_str = end.strftime("%d/%m/%Y")
    keysearch = f"{from_str}|{to_str}||0|3|'VND'|0|0"
    
    try:
        raw = http_post(HNX_AUCTION_URL, {
            "p_keysearch": keysearch,
            "pColOrder": "", "pOrderType": "",
            "pCurrentPage": "1", "pRecordOnPage": "200", "pIsSearch": "1",
        })
    except Exception:
        return []
    
    # Decode HTML entities (HNX dùng &#224; etc.)
    decoded = html_mod.unescape(raw)
    
    if "_tableDatas" not in decoded or len(decoded) < 500:
        return []
    
    # Find tbody
    tbody_match = re.search(r'<tbody>(.*?)</tbody>', decoded, re.DOTALL | re.IGNORECASE)
    if not tbody_match:
        return []
    
    rows = []
    tr_list = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_match.group(1), re.DOTALL | re.IGNORECASE)
    
    for tr in tr_list:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL | re.IGNORECASE)
        if len(tds) < 15:
            continue
        cells = [html_mod.unescape(re.sub(r"<[^>]+>", "", td).strip()) for td in tds]
        
        # Col 5 = Kỳ hạn ("15 Năm", "3 Năm", "10 Năm")
        tenor_raw = cells[5] if len(cells) > 5 else ""
        tenor = None
        for years in ["30", "20", "15", "10", "7", "5", "3", "2", "1"]:
            if f"{years} Năm" in tenor_raw or f"{years} năm" in tenor_raw:
                tenor = f"{years}Y"
                break
        if not tenor:
            continue
        
        # Col 9 = GT gọi thầu (raw VND), Col 11 = GT trúng thầu, Col 18 = LSTT
        offered_raw = parse_vn_float(cells[9]) if len(cells) > 9 else None  # GT gọi thầu
        sold_raw = parse_vn_float(cells[11]) if len(cells) > 11 else None   # GT trúng thầu
        cut_yield = parse_vn_float(cells[18]) if len(cells) > 18 else None  # Lãi suất trúng thầu
        
        # Convert raw VND to tỷ VND (HNX stores in raw VND: 1.000.000.000.000 = 1000 tỷ)
        offered_b = offered_raw / 1e9 if offered_raw and offered_raw > 1e6 else offered_raw
        sold_b = sold_raw / 1e9 if sold_raw and sold_raw > 1e6 else sold_raw
        
        # Date từ col 6
        date_str = cells[6] if len(cells) > 6 else ""
        date_match = re.match(r"(\d{2})/(\d{2})/(\d{4})", date_str)
        iso_date = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}" if date_match else None
        
        # Tỷ lệ trúng = sold/offered
        win_pct = (sold_b / offered_b * 100) if (offered_b and sold_b and offered_b > 0) else 0
        
        rows.append({
            "date": iso_date,
            "tenor": tenor,
            "offered_b_vnd": offered_b,
            "sold_b_vnd": sold_b,
            "win_pct": round(win_pct, 1),
            "cut_yield": cut_yield,
        })
    return rows


def fetch_fred_series(series_id: str, start: date, end: date) -> list[dict]:
    """Fetch FRED series. Port từ Bond Lab fred_global.py (chunk 90 ngày).
    
    Requires FRED_API_KEY env var.
    """
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return []
    
    # Chunk by 90 days (Bond Lab pattern)
    all_obs = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=90), end)
        params = urllib.parse.urlencode({
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": chunk_start.isoformat(),
            "observation_end": chunk_end.isoformat(),
        })
        try:
            resp_text = http_get(f"{FRED_URL}?{params}")
            payload = json.loads(resp_text)
            for obs in payload.get("observations", []):
                val = obs.get("value", ".")
                if val != ".":
                    all_obs.append({
                        "date": obs["date"],
                        "value": float(val),
                    })
        except Exception:
            pass
        chunk_start = chunk_end + timedelta(days=1)
    
    return all_obs


def fetch_all_chart_data(weeks: int = 12, target_week: str = None) -> dict:
    """Fetch all 5 chart datasets for the last N weeks. Returns JSON-serializable dict.

    Args:
        weeks: Number of weeks of history to fetch
        target_week: ISO week string like "2026-W26". If provided, end date = Friday of that week.
                     If None, defaults to most recent Friday.
    """
    if target_week:
        year_str, week_str = target_week.split("-W")
        year, week = int(year_str), int(week_str)
        end = date.fromisocalendar(year, week, 5)  # Friday
    else:
        # Most recent Friday
        today = date.today()
        days_since_friday = (today.weekday() - 4) % 7
        end = today - timedelta(days=days_since_friday)
    start = end - timedelta(weeks=weeks)
    
    print(f"Fetching chart data: {start} → {end} ({weeks} weeks)")
    
    data = {}
    
    # 1. HNX yield curve (3 tenors, daily)
    print("  HNX yield curve 2Y/5Y/10Y...")
    yields = fetch_hnx_yield_range(start, end, ["2Y", "5Y", "10Y"])
    data["yields"] = yields
    print(f"    {len(yields)} data points")
    
    # 2. HNX auction (weekly)
    print("  HNX auction results...")
    auctions = fetch_hnx_auction_range(start, end)
    data["auctions"] = auctions
    print(f"    {len(auctions)} auction rows")
    
    # 3. FRED US 10Y
    print("  FRED DGS10...")
    us10y = fetch_fred_series("DGS10", start, end)
    data["us_10y"] = us10y
    print(f"    {len(us10y)} observations")
    
    # 4. FRED DXY
    print("  FRED DTWEXBGS (DXY proxy)...")
    dxy = fetch_fred_series("DTWEXBGS", start, end)
    data["dxy"] = dxy
    print(f"    {len(dxy)} observations")
    
    return data


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=12)
    parser.add_argument("--week", default=None, help="Target ISO week, e.g. 2026-W26")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    
    data = fetch_all_chart_data(args.weeks, target_week=args.week)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
