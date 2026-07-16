"""fetch_sources.py — Fetch 12 PDFs (3 sources × 4 weeks) + upstream.

3 PDF sources:
  - SBV: sbv.gov.vn bulletin (PDF embed, UUID must be scraped from article)
  - VBMA: vbma.org.vn weekly report (direct download, %20 in URL, spacing varies)
  - VNBA: vnba.org.vn article → CDN PDF (md5/expires token present but unenforced)

Upstream sources (portable, no local API):
  - FRED (JSON, needs FRED_API_KEY env) — US 10Y/2Y, DXY
  - vnstock (Python lib) — VN-Index weekly

Usage:
  python3 fetch_sources.py --week 2026-W26 --out ./sources_cache
  python3 fetch_sources.py --week 2026-W26 --out ./sources_cache --upstream-only
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SBV_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "vi,en;q=0.9",
    "Referer": "https://www.sbv.gov.vn/vi/web/sbv_portal/thong-tin-ve-hoat-dong-ngan-hang-trong-tuan",
}


@dataclass
class WeekRange:
    """ISO week + Mon-Fri dates."""
    iso_week: str  # "2026-W26"
    monday: date
    friday: date

    @property
    def sbv_slug(self) -> str:
        """SBV article URL slug: '01-05.6.2026' (zero-padded day, dot-separated, unpadded month).

        SBV requires zero-padded day-of-month ('01-05' OK, '1-5' → 404).
        Month is NOT padded ('6' not '06'). Year full.
        """
        return f"{self.monday.day:02d}-{self.friday.day:02d}.{self.monday.month}.{self.monday.year}"

    @property
    def vbma_filename(self) -> str:
        """VBMA filename date part: '22062026-26062026' (zero-padded)."""
        return f"{self.monday.strftime('%d%m%Y')}-{self.friday.strftime('%d%m%Y')}"


def enumerate_4_weeks(target_iso_week: str) -> list[WeekRange]:
    """Return [N-3, N-2, N-1, N] as WeekRange objects.

    Handles year roll (W01 ← previous year's last week).
    """
    year_str, week_str = target_iso_week.split("-W")
    year, week = int(year_str), int(week_str)
    weeks = []
    for w in range(week - 3, week + 1):
        if w < 1:
            prev_year = year - 1
            # ISO last week of prev year (52 or 53)
            try:
                last_week = date(prev_year, 12, 28).isocalendar()[1]
            except ValueError:
                last_week = 52
            w_use, y_use = last_week + w, prev_year
        else:
            w_use, y_use = w, year
        monday = date.fromisocalendar(y_use, w_use, 1)
        friday = date.fromisocalendar(y_use, w_use, 5)
        weeks.append(WeekRange(f"{y_use}-W{w_use:02d}", monday, friday))
    return weeks


def curl(url: str, headers: Optional[dict] = None, sleep_s: float = 0.0) -> bytes:
    """HTTP GET returning bytes, with optional sleep (SBV WAF avoidance)."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    if sleep_s:
        time.sleep(sleep_s)
    return data


def pdftotext(pdf_path: Path, txt_path: Path) -> None:
    """Convert PDF to text via system pdftotext -layout."""
    subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
        check=True, capture_output=True,
    )


def fetch_sbv_week(week: WeekRange, out_dir: Path) -> Optional[Path]:
    """Fetch SBV weekly bulletin PDF → .txt. Returns None if week skipped (holiday).

    The article slug is 'diễn-biến-...-tuần-từ-{D1}-{D2}.{M}.{Y}' (Vietnamese
    with diacritics). We URL-encode the full slug. SBV accepts both /vi/w/ and
    /vi/web/sbv_portal/w/ forms — we use the latter (canonical).
    """
    slug_vi = f"diễn-biến-thị-trường-ngoại-tệ-và-thị-trường-liên-ngân-hàng-tuần-từ-{week.sbv_slug}"
    article_url = "https://www.sbv.gov.vn/vi/web/sbv_portal/w/" + quote(slug_vi)
    try:
        html = curl(article_url, headers=SBV_HEADERS, sleep_s=3).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # holiday skip
        raise
    # The PDF URL is /documents/20117/0/{dates}.pdf/{uuid}?t=... — UUID mandatory.
    pdf_match = re.search(r'(?:src|href)="(/documents/20117/0/[^"]+\.pdf/[^"]+)"', html)
    if not pdf_match:
        return None
    pdf_url = "https://www.sbv.gov.vn" + pdf_match.group(1)
    pdf_path = out_dir / f"sbv_{week.iso_week}.pdf"
    txt_path = out_dir / f"sbv_{week.iso_week}.txt"
    pdf_path.write_bytes(curl(pdf_url, headers=SBV_HEADERS))
    pdftotext(pdf_path, txt_path)
    return txt_path


def fetch_vbma_by_weeks(out_dir: Path, target_weeks: list) -> dict:
    """Fetch VBMA PDFs for specific ISO weeks by scanning listing pages."""
    from datetime import date as _date
    import time as _time

    results = {}
    remaining = list(target_weeks)

    # Check cache first
    for tw in list(remaining):
        w_short = tw.split("-")[-1]
        cached = out_dir / f"vbma_{w_short}.txt"
        if cached.exists():
            results[w_short] = cached
            remaining.remove(tw)

    if not remaining:
        print(f"  VBMA: all {len(target_weeks)} weeks cached")
        return results

    print(f"  VBMA: fetching {len(remaining)}: {[tw.split('-')[-1] for tw in remaining]}")

    # Scan listing pages to collect PDF hrefs
    all_hrefs = []
    for page in range(1, 6):
        try:
            html = curl(f"https://vbma.org.vn/vi/reports/weekly?page={page}").decode("utf-8", errors="ignore")
            hrefs = re.findall(r'href="(/storage/reports/[^"]+\.pdf)"', html)
            all_hrefs.extend(hrefs)
            if len(hrefs) < 12:
                break
            _time.sleep(0.5)
        except Exception:
            break

    # Download + match by date
    for href in all_hrefs:
        if not remaining:
            break
        pdf_url = "https://vbma.org.vn" + href.replace(" ", "%20")
        tmp_pdf = out_dir / f"vbma_tmp_{len(results)}.pdf"
        tmp_txt = out_dir / f"vbma_tmp_{len(results)}.txt"
        try:
            tmp_pdf.write_bytes(curl(pdf_url))
            pdftotext(tmp_pdf, tmp_txt)
            text = tmp_txt.read_text(encoding="utf-8", errors="ignore")
            dates_found = re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", text[:3000])
            matched = False
            for d_str, m_str, y_str in dates_found[:5]:
                try:
                    d_val = _date(int(y_str), int(m_str), int(d_str))
                    iso = d_val.isocalendar()
                    tw_key = f"{iso[0]}-W{iso[1]:02d}"
                    if tw_key in remaining:
                        w_short = tw_key.split("-")[-1]
                        final_txt = out_dir / f"vbma_{w_short}.txt"
                        final_pdf = out_dir / f"vbma_{w_short}.pdf"
                        tmp_txt.rename(final_txt)
                        tmp_pdf.rename(final_pdf)
                        results[w_short] = final_txt
                        remaining.remove(tw_key)
                        print(f"    {w_short}: matched ({d_val})")
                        matched = True
                        break
                except ValueError:
                    continue
            if not matched:
                tmp_pdf.unlink(missing_ok=True)
                tmp_txt.unlink(missing_ok=True)
        except Exception:
            tmp_pdf.unlink(missing_ok=True)
            tmp_txt.unlink(missing_ok=True)

    if remaining:
        print(f"  ⚠️ VBMA not found: {[tw.split('-')[-1] for tw in remaining]}")
    return results


def fetch_vnba_by_weeks(out_dir: Path, target_weeks: list) -> dict:
    """Fetch VNBA PDFs for specific ISO weeks via sidebar chain crawling.

    Strategy: start from known recent article → follow sidebar links backward.
    Handle 429 rate limit with sleep + retry.
    """
    import ssl as _ssl
    import time as _time
    from datetime import date as _date

    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE

    results = {}
    remaining = list(target_weeks)

    # Check cache first
    for tw in list(remaining):
        w_short = tw.split("-")[-1]
        cached = out_dir / f"vnba_{w_short}.txt"
        if cached.exists():
            results[w_short] = cached
            remaining.remove(tw)

    if not remaining:
        print(f"  VNBA: all {len(target_weeks)} weeks cached")
        return results

    print(f"  VNBA: fetching {len(remaining)}: {[tw.split('-')[-1] for tw in remaining]}")

    def fetch_url(url, retries=3):
        """Fetch with retry on 429."""
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                return urllib.request.urlopen(req, timeout=20, context=ctx).read().decode("utf-8", errors="ignore")
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    _time.sleep(3 * (attempt + 1))
                    continue
                return None
            except Exception:
                _time.sleep(1)
                continue
        return None

    # Find starting point — hashtag or known article
    start_url = None
    for week_n in [4, 3, 5]:
        html = fetch_url(f"https://vnba.org.vn/vi/hashtag/kinh-te-tai-chinh-tien-te-tuan-{week_n}")
        if html:
            articles = re.findall(r'/vi/ban-tin-kinh-te-tai-chinh-tien-te-tuan-\d+-thang-\d+-\d+-\d+\.htm', html)
            if articles:
                start_url = "https://vnba.org.vn" + sorted(set(articles))[-1]
                break
    if not start_url:
        start_url = "https://vnba.org.vn/vi/ban-tin-kinh-te-tai-chinh-tien-te-tuan-4-thang-6-2026-22424.htm"

    # Chain crawl: follow sidebar backward
    current_url = start_url
    max_chain = 15  # safety limit

    for step in range(max_chain):
        if not remaining:
            break

        _time.sleep(1.5)  # rate limit protection
        html = fetch_url(current_url)
        if not html:
            continue

        # Extract CDN PDF
        cdn_match = re.search(r'(https://s-vnba-cdn\.aicms\.vn/[^"]+\.pdf)', html)
        if cdn_match:
            pdf_url = cdn_match.group(1)
            pdf_path = out_dir / f"vnba_tmp_{step}.pdf"
            txt_path = out_dir / f"vnba_tmp_{step}.txt"
            try:
                pdf_path.write_bytes(curl(pdf_url))
                pdftotext(pdf_path, txt_path)
                text = txt_path.read_text(encoding="utf-8", errors="ignore")

                # Match against target weeks
                dates_found = re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", text[:2000])
                # Also try title-based: "tuần N tháng M/YYYY"
                title_match = re.search(r'tuần\s*(\d+)\s*tháng\s*(\d+)\s*/?\s*(\d{4})', text[:500], re.I)

                matched = False
                for d_str, m_str, y_str in dates_found[:3]:
                    try:
                        d_val = _date(int(y_str), int(m_str), int(d_str))
                        iso = d_val.isocalendar()
                        tw_key = f"{iso[0]}-W{iso[1]:02d}"
                        if tw_key in remaining:
                            w_short = tw_key.split("-")[-1]
                            final_txt = out_dir / f"vnba_{w_short}.txt"
                            final_pdf = out_dir / f"vnba_{w_short}.pdf"
                            txt_path.rename(final_txt)
                            pdf_path.rename(final_pdf)
                            results[w_short] = final_txt
                            remaining.remove(tw_key)
                            print(f"    VNBA {w_short}: matched ({d_val})")
                            matched = True
                            break
                    except ValueError:
                        continue

                # Also check monthly variant: "tháng M + tuần 1 tháng M+1" = first week of M+1
                if not matched and title_match:
                    wn, mo, y = int(title_match.group(1)), int(title_match.group(2)), int(title_match.group(3))
                    if "tháng" in text[:200].lower() and "va" in text[:200].lower():
                        # Monthly variant — covers end of prev month + start of this month
                        approx_day = min((wn - 1) * 7 + 3, 25)
                        try:
                            iso = _date(y, mo, approx_day).isocalendar()
                            tw_key = f"{iso[0]}-W{iso[1]:02d}"
                            if tw_key in remaining:
                                w_short = tw_key.split("-")[-1]
                                final_txt = out_dir / f"vnba_{w_short}.txt"
                                final_pdf = out_dir / f"vnba_{w_short}.pdf"
                                txt_path.rename(final_txt)
                                pdf_path.rename(final_pdf)
                                results[w_short] = final_txt
                                remaining.remove(tw_key)
                                print(f"    VNBA {w_short}: matched (tuan {wn} thang {mo})")
                                matched = True
                        except ValueError:
                            pass

                if not matched:
                    txt_path.unlink(missing_ok=True)
                    pdf_path.unlink(missing_ok=True)
            except Exception:
                txt_path.unlink(missing_ok=True)
                pdf_path.unlink(missing_ok=True)

        # Find next (older) article in sidebar
        current_id_m = re.search(r'-(\d+)\.htm', current_url)
        if not current_id_m:
            break
        current_id = int(current_id_m.group(1))
        sidebar_links = re.findall(r'/vi/ban-tin-kinh-te-tai-chinh-tien-te-[^"]+\.htm', html)
        older = []
        for link in sidebar_links:
            id_m = re.search(r'-(\d+)\.htm', link)
            if id_m and int(id_m.group(1)) < current_id:
                older.append((int(id_m.group(1)), link))

        if older:
            # Go to the next most recent older article
            older.sort(key=lambda x: x[0], reverse=True)
            current_url = "https://vnba.org.vn" + older[0][1]
        else:
            break

    if remaining:
        print(f"  ⚠️ VNBA not found: {[tw.split('-')[-1] for tw in remaining]}")
    return results
    """Fetch N most-recent VNBA weekly bulletins.

    Strategy: VNBA không có category page. Thay vào đó:
    1. Bắt đầu từ 1 bài biết gần nhất (hardcoded fallback hoặc từ hashtag)
    2. Scrape sidebar links từ bài đó → tìm các bài khác
    3. Sort by article ID (monotonic = chronological) → lấy N gần nhất
    4. Follow từng bài → extract CDN PDF → download
    """
    import ssl as _ssl
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE

    # Bước 1: Tìm bài gần nhất — thử hashtag tuần 4, rồi tuần 3
    start_url = None
    for week_n in [4, 3, 5, 2]:
        hashtag_url = f"https://vnba.org.vn/vi/hashtag/kinh-te-tai-chinh-tien-te-tuan-{week_n}"
        try:
            req = urllib.request.Request(hashtag_url, headers={"User-Agent": USER_AGENT})
            html = urllib.request.urlopen(req, timeout=15, context=ctx).read().decode("utf-8", errors="ignore")
            articles = re.findall(r'/vi/ban-tin-kinh-te-tai-chinh-tien-te-tuan-\d+-thang-\d+-\d+-\d+\.htm', html)
            if articles:
                start_url = "https://vnba.org.vn" + sorted(set(articles))[-1]
                break
        except Exception:
            continue

    # Fallback: hardcoded bài gần nhất (update khi cần)
    if not start_url:
        start_url = "https://vnba.org.vn/vi/ban-tin-kinh-te-tai-chinh-tien-te-tuan-4-thang-6-2026-22424.htm"

    # Bước 2: Scrape sidebar từ bài gần nhất
    try:
        req = urllib.request.Request(start_url, headers={"User-Agent": USER_AGENT})
        html = urllib.request.urlopen(req, timeout=15, context=ctx).read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    sidebar_links = sorted(set(re.findall(r'/vi/ban-tin-kinh-te-tai-chinh-tien-te-[^"]+\.htm', html)))
    # Thêm chính bài start vào list
    start_path = "/" + start_url.split("/", 3)[-1]
    if start_path not in sidebar_links:
        sidebar_links.append(start_path)

    # Bước 3: Parse week/month/year/id → sort by ID
    parsed = []
    for link in sidebar_links:
        m = re.search(r'tuan-(\d+)-thang-(\d+)-(\d+)-(\d+)', link)
        if m:
            parsed.append({"link": link, "id": int(m.group(4)),
                          "week_n": int(m.group(1)), "month": int(m.group(2)), "year": int(m.group(3))})
            continue
        m2 = re.search(r'thang-(\d+)-va-tuan-1-thang-(\d+)-(\d+)-(\d+)', link)
        if m2:
            parsed.append({"link": link, "id": int(m2.group(4)),
                          "week_n": 1, "month": int(m2.group(2)), "year": int(m2.group(3))})

    parsed.sort(key=lambda x: x["id"], reverse=True)
    recent = parsed[:count]

    if len(recent) < count:
        print(f"  ⚠️ VNBA: chỉ tìm thấy {len(recent)} bài (cần {count})")

    # Bước 4: Fetch từng bài → extract CDN PDF → download + rename
    results = {}
    for item in recent:
        art_url = "https://vnba.org.vn" + item["link"]
        try:
            req = urllib.request.Request(art_url, headers={"User-Agent": USER_AGENT})
            art_html = urllib.request.urlopen(req, timeout=15, context=ctx).read().decode("utf-8", errors="ignore")
        except Exception:
            continue

        cdn_match = re.search(r'(https://s-vnba-cdn\.aicms\.vn/[^"]+\.pdf)', art_html)
        if not cdn_match:
            continue

        pdf_url = cdn_match.group(1)

        # Determine ISO week — for "thang-X-va-tuan-1-thang-Y" use day 3 of target month
        from datetime import date as _date
        if "thang-" in item["link"] and item["link"].count("thang-") > 1:
            # Monthly variant "thang-5-va-tuan-1-thang-6" → use day 3 of month Y (first ISO week)
            try:
                iso = _date(item["year"], item["month"], 3).isocalendar()
                week_short = f"W{iso[1]:02d}"
            except ValueError:
                week_short = f"tuan{item['week_n']}_thang{item['month']}"
        else:
            # Regular: use mid-week day to approximate ISO week
            approx_day = min((item["week_n"] - 1) * 7 + 3, 25)
            try:
                iso = _date(item["year"], item["month"], approx_day).isocalendar()
                week_short = f"W{iso[1]:02d}"
            except ValueError:
                week_short = f"tuan{item['week_n']}_thang{item['month']}"

        pdf_path = out_dir / f"vnba_{week_short}.pdf"
        txt_path = out_dir / f"vnba_{week_short}.txt"

        # Skip if already exists
        if txt_path.exists():
            print(f"  VNBA {week_short}: cached")
            results[f"vnba_{week_short}"] = txt_path
            continue

        try:
            pdf_path.write_bytes(curl(pdf_url))
            pdftotext(pdf_path, txt_path)
            print(f"  VNBA {week_short}: fetched ({txt_path.stat().st_size:,} chars)")
            results[f"vnba_{week_short}"] = txt_path
        except Exception as e:
            print(f"  VNBA {week_short}: ERROR {e}")

    return results


def fetch_fred_series(series_id: str, weeks: int = 12) -> list[dict]:
    """Fetch FRED series observations for the last N weeks. Needs FRED_API_KEY."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return []  # upstream_skip — caller handles
    end = date.today()
    start = end - timedelta(weeks=weeks)
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
        f"&observation_start={start.isoformat()}&observation_end={end.isoformat()}"
    )
    data = curl(url)
    payload = json.loads(data)
    return payload.get("observations", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True, help="Target ISO week, e.g. 2026-W26")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--upstream-only", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.upstream_only:
        weeks = enumerate_4_weeks(args.week)
        print(f"Enumerated weeks: {[w.iso_week for w in weeks]}")
        for w in weeks:
            try:
                txt = fetch_sbv_week(w, out_dir)
                status = txt.name if txt else "SKIP (holiday?)"
            except Exception as e:
                status = f"ERROR: {e}"
            print(f"  SBV {w.iso_week}: {status}")
        try:
            vbma = fetch_vbma_recent(out_dir)
            print(f"  VBMA: fetched {len(vbma)} PDFs")
        except Exception as e:
            print(f"  VBMA: ERROR: {e}")
        try:
            vnba = fetch_vnba_recent(out_dir)
            print(f"  VNBA: fetched {len(vnba)} PDFs")
        except Exception as e:
            print(f"  VNBA: ERROR: {e}")

    # Upstream (always attempt, gracefully skip if no key)
    fred_10y = fetch_fred_series("DGS10", weeks=12)
    print(f"  FRED DGS10: {len(fred_10y)} observations")
    fred_dxy = fetch_fred_series("DTWEXBGS", weeks=12)
    print(f"  FRED DXY: {len(fred_dxy)} observations")


if __name__ == "__main__":
    main()
