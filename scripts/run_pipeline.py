#!/usr/bin/env python3
"""run_pipeline.py — Full automation pipeline cho vn-rates-weekly.

1 lệnh duy nhất → report.html ready to deploy.

Usage:
  python3 scripts/run_pipeline.py --week 2026-W27 --out ./output/

Pipeline:
  0. Check deps
  1. Pre-flight (HEAD check sources)
  2. Fetch PDFs (SBV+VBMA+VNBA)
  3. Fetch upstream (HNX yield + auction + FRED)
  4. Build report.json (extract + data-driven prose)
  5. Verify data (exit 1 nếu mismatch)
  6. Render polished HTML (charts + tables + narrative)
  7. Audit gates (HTML structure + JS + banned words)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
SKILL_DIR = SCRIPTS_DIR.parent


def step(msg: str):
    print(f"\n{'═'*60}")
    print(f"  {msg}")
    print(f"{'═'*60}")


def run(cmd: list[str], desc: str) -> bool:
    """Run subprocess, return True if success."""
    print(f"  → {' '.join(cmd[:4])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  ❌ {desc} FAILED (exit {result.returncode})")
        if result.stderr:
            print(f"     {result.stderr[:300]}")
        return False
    if result.stdout:
        # Print last 3 lines
        lines = result.stdout.strip().split("\n")
        for line in lines[-3:]:
            print(f"  {line}")
    print(f"  ✅ {desc}")
    return True


def check_deps() -> bool:
    """Bước 0: Check dependencies."""
    step("BƯỚC 0: Check dependencies")
    deps = {"pdftotext": shutil.which("pdftotext"), "node": shutil.which("node")}
    fred_key = os.environ.get("FRED_API_KEY")

    all_ok = True
    for name, path in deps.items():
        if path:
            print(f"  ✅ {name}: {path}")
        else:
            print(f"  ❌ {name}: NOT FOUND")
            all_ok = False

    if fred_key:
        print(f"  ✅ FRED_API_KEY: set")
    else:
        print(f"  ⚠️ FRED_API_KEY: not set (FRED charts will be skipped)")

    return all_ok


def preflight(week: str) -> bool:
    """Bước 1: Basic pre-flight check."""
    step("BƯỚC 1: Pre-flight")
    year_str, week_str = week.split("-W")
    year, week_num = int(year_str), int(week_str)

    # Compute 4 weeks
    weeks = []
    for w in range(week_num - 3, week_num + 1):
        if w < 1:
            prev_year = year - 1
            try:
                last_week = date(prev_year, 12, 28).isocalendar()[1]
            except Exception:
                last_week = 52
            weeks.append(f"{prev_year}-W{last_week + w:02d}")
        else:
            weeks.append(f"{year}-W{w:02d}")

    friday = date.fromisocalendar(year, week_num, 5)
    print(f"  Target week: {week} (Friday {friday})")
    print(f"  4-week window: {weeks}")

    # Quick connectivity check (SBV)
    try:
        import urllib.request
        ssl_ctx = __import__("ssl").create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = __import__("ssl").CERT_NONE
        req = urllib.request.Request("https://vbma.org.vn/vi/reports/weekly?page=1",
                                     headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
        print("  ✅ VBMA reachable")
    except Exception as e:
        print(f"  ⚠️ VBMA check: {e}")

    return True


def fetch_pdfs(week: str, cache_dir: Path) -> bool:
    """Bước 2: Fetch PDFs — rolling cache + by-week strategy.

    Uses fetch_vbma_by_weeks + fetch_vnba_by_weeks for precise week targeting.
    Falls back to fetch_sources.py for SBV (already week-parameterized).
    """
    step("BƯỚC 2: Fetch PDFs (rolling cache)")

    year_str, week_str = week.split("-W")
    year, week_num = int(year_str), int(week_str)

    # Compute 4 target weeks
    target_weeks = []
    for w in range(week_num - 3, week_num + 1):
        if w < 1:
            prev_year = year - 1
            try:
                last_week = date(prev_year, 12, 28).isocalendar()[1]
            except Exception:
                last_week = 52
            target_weeks.append(f"{prev_year}-W{last_week + w:02d}")
        else:
            target_weeks.append(f"{year}-W{w:02d}")

    # Check cache — which weeks already have all 3 sources?
    existing = []
    missing = []
    for w in target_weeks:
        w_short = w.split("-")[-1]
        has_sbv = (cache_dir / f"sbv_{w}.txt").exists()
        has_vbma = (cache_dir / f"vbma_{w_short}.txt").exists()
        has_vnba = (cache_dir / f"vnba_{w_short}.txt").exists()
        if has_sbv and has_vbma and has_vnba:
            existing.append(w)
        else:
            missing.append(w)

    print(f"  Cache check: {len(existing)}/{len(target_weeks)} weeks fully cached")
    for w in target_weeks:
        status = "✅ cached" if w in existing else "❌ missing"
        print(f"    {w}: {status}")

    if not missing:
        print("  ✅ All 4 weeks cached — skip fetch")
    else:
        # 1. Fetch SBV for missing weeks (already week-parameterized)
        for w in missing:
            w_short = w.split("-")[-1]
            if not (cache_dir / f"sbv_{w}.txt").exists():
                print(f"\n  → SBV {w}...")
                ok = run(
                    [sys.executable, str(SCRIPTS_DIR / "fetch_sources.py"), "--week", w, "--out", str(cache_dir)],
                    f"SBV {w}"
                )
                if not ok:
                    print(f"\n⚠️ SBV {w} fetch failed — continuing")

        # 2. Fetch VBMA for missing weeks using by_weeks
        missing_vbma = [w for w in missing if not (cache_dir / f"vbma_{w.split('-')[-1]}.txt").exists()]
        if missing_vbma:
            print(f"\n  → VBMA {len(missing_vbma)} week(s)...")
            sys.path.insert(0, str(SCRIPTS_DIR))
            from fetch_sources import fetch_vbma_by_weeks
            fetch_vbma_by_weeks(cache_dir, missing_vbma)

        # 3. Fetch VNBA for missing weeks using by_weeks
        missing_vnba = [w for w in missing if not (cache_dir / f"vnba_{w.split('-')[-1]}.txt").exists()]
        if missing_vnba:
            print(f"\n  → VNBA {len(missing_vnba)} week(s)...")
            from fetch_sources import fetch_vnba_by_weeks
            fetch_vnba_by_weeks(cache_dir, missing_vnba)

    # Cleanup: remove weeks older than 5
    cutoff_week = week_num - 5
    removed = 0
    for pattern in ["sbv_*.txt", "sbv_*.pdf"]:
        for f in cache_dir.glob(pattern):
            m = re.search(r'(\d{4})-W(\d{2})', f.name)
            if m:
                f_year, f_week = int(m.group(1)), int(m.group(2))
                if f_year < year or (f_year == year and f_week < cutoff_week):
                    f.unlink()
                    removed += 1
    for pattern in ["vbma_W*.txt", "vbma_W*.pdf", "vnba_W*.txt", "vnba_W*.pdf"]:
        for f in cache_dir.glob(pattern):
            m = re.search(r'W(\d{2})', f.name)
            if m:
                f_week = int(m.group(1))
                if f_week < cutoff_week:
                    f.unlink()
                    removed += 1
    if removed > 0:
        print(f"\n  🗑️ Cleaned {removed} old file(s) (>5 weeks)")

    return True


def fetch_upstream(week: str, out_dir: Path) -> bool:
    """Bước 3: Fetch upstream chart data (HNX + FRED)."""
    step("BƯỚC 3: Fetch upstream (HNX + FRED)")
    chart_data_path = out_dir / "chart_data.json"
    return run(
        [sys.executable, str(SCRIPTS_DIR / "upstream_fetch.py"), "--week", week, "--out", str(chart_data_path)],
        "Fetch upstream chart data"
    )


def build_report(week: str, cache_dir: Path, out_dir: Path) -> bool:
    """Bước 4: Build report.json."""
    step("BƯỚC 4: Build report.json")
    report_path = out_dir / "report.json"
    return run(
        [sys.executable, str(SCRIPTS_DIR / "build_report_v2.py"), "--week", week,
         "--cache", str(cache_dir), "--out", str(report_path)],
        "Build report"
    )


def verify_data(cache_dir: Path, out_dir: Path) -> bool:
    """Bước 5: Verify data accuracy."""
    step("BƯỚC 5: Data verification")
    return run(
        [sys.executable, str(SCRIPTS_DIR / "verify_data.py"),
         "--report", str(out_dir / "report.json"), "--cache", str(cache_dir)],
        "Data verification"
    )


def render_html(out_dir: Path) -> bool:
    """Bước 6: Render polished HTML report."""
    step("BƯỚC 6: Render polished HTML")

    report_path = out_dir / "report.json"
    html_path = out_dir / "report.html"

    # Use render_report_v2 (data-driven, reads report.json)
    return run(
        [sys.executable, str(SCRIPTS_DIR / "render_polished.py"),
         "--report", str(report_path), "--out", str(html_path)],
        "Render polished HTML"
    )


def audit_gates(html_path: Path) -> bool:
    """Bước 7: Audit gates (HTML structure + JS + banned words)."""
    step("BƯỚC 7: Audit gates")
    return run(
        [sys.executable, str(SCRIPTS_DIR / "audit_gate.py"), "--html", str(html_path)],
        "Audit gates"
    )


def main():
    parser = argparse.ArgumentParser(description="Full automation pipeline cho vn-rates-weekly")
    parser.add_argument("--week", required=True, help="Target ISO week, e.g. 2026-W27")
    parser.add_argument("--out", default="./output", help="Output directory")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetch (use existing cache)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    cache_dir = out_dir / "sources_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🚀 vn-rates-weekly pipeline — {args.week}")
    print(f"   Output: {out_dir.absolute()}")

    # Bước 0: Check deps
    if not check_deps():
        print("\n❌ Dependencies missing. Install pdftotext (poppler) + node first.")
        sys.exit(1)

    # Bước 1: Pre-flight
    if not preflight(args.week):
        sys.exit(1)

    # Bước 2: Fetch PDFs
    if not args.skip_fetch:
        if not fetch_pdfs(args.week, cache_dir):
            print("\n❌ Pipeline FAILED at fetch PDFs")
            sys.exit(1)

    # Bước 3: Fetch upstream
    if not fetch_upstream(args.week, out_dir):
        print("\n⚠️ Upstream fetch failed — charts will use PDF data only")

    # Bước 4: Build report
    if not build_report(args.week, cache_dir, out_dir):
        print("\n❌ Pipeline FAILED at build report")
        sys.exit(1)

    # Bước 5: Verify data
    if not verify_data(cache_dir, out_dir):
        print("\n❌ Pipeline FAILED at data verification")
        sys.exit(1)

    # Bước 6: Render polished HTML
    if not render_html(out_dir):
        print("\n❌ Pipeline FAILED at render")
        sys.exit(1)

    # Bước 7: Audit gates
    html_path = out_dir / "report.html"
    if not audit_gates(html_path):
        print("\n❌ Pipeline FAILED at audit gates")
        sys.exit(1)

    # Done
    print(f"\n{'═'*60}")
    print(f"  ✅ PIPELINE COMPLETE")
    print(f"{'═'*60}")
    print(f"\n  Report: {html_path.absolute()}")
    print(f"  Size: {html_path.stat().st_size:,} bytes")
    print(f"\n  Deploy:")
    print(f"    cp {html_path} deploy/index.html && cd deploy && vercel --prod")


if __name__ == "__main__":
    main()
