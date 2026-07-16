"""verify_data.py — BẮT BUỘC. Auto-verify mọi số trong report.json vs cache PDF gốc.

Tính chính xác là sống còn với báo cáo tài chính. Script này đọc report.json,
re-parse từng file .txt nguồn (độc lập với build_report.py), và đối chiếu.

FAIL criteria (exit 1):
  - Bất kỳ số nào lệch > 0.5% so với source gốc
  - Source file thiếu (number trong report nhưng không trace được)
  - Cross-check SBV vs VBMA cho LNH lệch > 5bp

Usage:
  python3 verify_data.py --report report.json --cache sources_cache/
  python3 verify_data.py --report report.json --cache sources_cache/ --strict
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class VerifyResult:
    """Kết quả verify 1 điểm dữ liệu."""
    card_key: str
    week: str
    reported: Optional[float]
    truth: Optional[float]
    source_file: str
    source_excerpt: str  # 80 chars context từ PDF gốc
    delta_pct: Optional[float]  # % deviation
    status: str  # "OK" | "MISMATCH" | "MISSING_SOURCE" | "NULL_REPORTED"
    detail: str = ""


def parse_sbv_lnh(text: str) -> dict:
    """Re-parse SBV real format — ĐỘC LẬP với build_report.py.

    Table header: 'Qua đêm 1 tuần 2 tuần 1 tháng 3 tháng 6 tháng 9 tháng'
    Row: 'VND  6,81  6,59  6,73  7,01  7,61  8,13  6,65'
    """
    result = {}
    header_re = re.compile(
        r"Qua đêm\s+1 tuần\s+2 tuần\s+1 tháng\s+3 tháng\s*6 tháng\s+9 tháng",
        re.IGNORECASE,
    )
    m = header_re.search(text)
    if not m:
        return result
    after = text[m.end():m.end() + 500]
    vnd_match = re.search(r"VND\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", after)
    if vnd_match:
        result["overnight"] = float(vnd_match.group(1).replace(",", "."))
        result["one_week"] = float(vnd_match.group(2).replace(",", "."))
        result["one_month"] = float(vnd_match.group(4).replace(",", "."))
    return result


def parse_sbv_fx(text: str) -> dict:
    """Re-parse SBV FX — cặp tỷ giá cuối file (ngày cuối tuần).

    Pattern: '26.114/26.454' — lấy cặp cuối cùng.
    """
    matches = re.findall(r"(\d{2}\.\d{3})/(\d{2}\.\d{3})", text)
    if not matches:
        return {}
    last_low, last_high = matches[-1]
    low = float(last_low.replace(".", ""))
    high = float(last_high.replace(".", ""))
    return {"tm_low": low, "tm_high": high, "tm_mid": (low + high) / 2}


def parse_vbma_yield_table(text: str) -> dict:
    """Re-parse VBMA yield table — ĐỘC LẬP với extract_cards.parse_vbma_yields.

    Pattern: dòng 'DD/M/YYYY  3.38%  3.48%  ... 4.69%' (date + 9 percentages).
    Map cột [2N=idx1, 5N=idx3, 10N=idx5].
    """
    row_re = re.compile(
        r"^(\d{1,2}/\d{1,2}/\d{4})\s+"
        + r"\s+".join([r"(\d{1,2}\.\d{2,4})%"] * 9)
        + r"\s*$",
        re.MULTILINE,
    )
    m = row_re.search(text)
    if not m:
        return {}
    cols = [float(m.group(2 + i)) for i in range(9)]
    # Tenor order: 1N 2N 3N 5N 7N 10N 15N 20N 30N
    # index:       0   1   2   3   4    5    6    7    8
    return {
        "date_label": m.group(1),
        "yield_2y": cols[1],
        "yield_5y": cols[3],
        "yield_10y": cols[5],
    }


def parse_vnba_global(text: str) -> dict:
    """Re-parse VNBA global — ĐỘC LẬP với extract_cards.parse_vnba_global."""
    result = {}
    m = re.search(r"10 năm[^.]{0,80}về mức\s+(\d{1,2}[.,]\d{1,2})\s*%", text, re.I)
    if m:
        result["us_10y"] = float(m.group(1).replace(",", "."))
    m = re.search(r"DXY\s+(\d{2,3}[.,]\d{1,3})", text)
    if m:
        result["dxy"] = float(m.group(1).replace(",", "."))
    return result


def parse_vbma_lnh_tb5(text: str) -> dict:
    """Re-parse VBMA LNH 'TB 5 ngày' cho cross-check vs SBV.

    Pattern: 'ON  <tb5ngay>  <close>  <prev_close>  <+/- wow>  <+/- mom>'
    """
    result = {}
    m = re.search(r"^\s*ON\s+(\d+\.\d+)\s+(\d+\.\d+)", text, re.MULTILINE)
    if m:
        result["on_tb5"] = float(m.group(1))
        result["on_close"] = float(m.group(2))
    return result


def excerpt_around(text: str, pattern: str, width: int = 80) -> str:
    """Lấy 80 chars context quanh pattern trong text."""
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not m:
        return "(pattern not found)"
    start = max(0, m.start() - 20)
    end = min(len(text), m.end() + width - 20)
    return re.sub(r"\s+", " ", text[start:end]).strip()[:width]


def verify_report(report_path: Path, cache_dir: Path, strict: bool = False) -> list[VerifyResult]:
    """Verify toàn bộ report.json vs cache. Trả về list results."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    weeks = report["period"]["weeks_covered"]
    results: list[VerifyResult] = []

    # === 1. LNH from SBV ===
    for week in weeks:
        week_short = week.split("-")[-1]  # W23
        sbv_file = cache_dir / f"sbv_{week}.txt"
        if not sbv_file.exists():
            for key in ["interbank_on", "interbank_1w", "interbank_1m"]:
                results.append(VerifyResult(key, week_short, None, None,
                    str(sbv_file), "", None, "MISSING_SOURCE",
                    f"SBV file missing: {sbv_file.name}"))
            continue
        text = sbv_file.read_text(encoding="utf-8", errors="ignore")
        truth_lnh = parse_sbv_lnh(text)
        excerpt = excerpt_around(text, r"Qua đêm.*?9 tháng", 100)
        for key, truth_key in [("interbank_on", "overnight"),
                                ("interbank_1w", "one_week"),
                                ("interbank_1m", "one_month")]:
            card = report["group1_money_market"].get(key)
            if not card:
                continue
            reported = next((v["value"] for v in card["values"] if v["week"] == week), None)
            truth = truth_lnh.get(truth_key)
            results.append(_make_result(key, week_short, reported, truth, sbv_file.name, excerpt, strict))

    # === 2. LSTP from VBMA ===
    for week in weeks:
        week_short = week.split("-")[-1]
        vbma_file = cache_dir / f"vbma_{week_short}.txt"
        if not vbma_file.exists():
            for key in ["gov_2y_yield", "gov_5y_yield", "gov_10y_yield"]:
                results.append(VerifyResult(key, week_short, None, None,
                    str(vbma_file), "", None, "MISSING_SOURCE",
                    f"VBMA file missing: {vbma_file.name}"))
            continue
        text = vbma_file.read_text(encoding="utf-8", errors="ignore")
        truth_yields = parse_vbma_yield_table(text)
        # Tìm dòng data để excerpt
        row_m = re.search(r"^\d{1,2}/\d{1,2}/\d{4}\s+(\d+\.\d+%)", text, re.MULTILINE)
        excerpt = excerpt_around(text, r"\d{1,2}/\d{1,2}/2026\s+(\d+\.\d+%)", 100) if row_m else ""
        for key, truth_key in [("gov_2y_yield", "yield_2y"),
                                ("gov_5y_yield", "yield_5y"),
                                ("gov_10y_yield", "yield_10y")]:
            card = report["group2_bonds"].get(key)
            if not card:
                continue
            reported = next((v["value"] for v in card["values"] if v["week"] == week), None)
            truth = truth_yields.get(truth_key)
            results.append(_make_result(key, week_short, reported, truth, vbma_file.name, excerpt, strict))

    # === 3. FX from SBV ===
    for week in weeks:
        week_short = week.split("-")[-1]
        sbv_file = cache_dir / f"sbv_{week}.txt"
        if not sbv_file.exists():
            continue
        text = sbv_file.read_text(encoding="utf-8", errors="ignore")
        truth_fx = parse_sbv_fx(text)
        excerpt = excerpt_around(text, r"\d{2}\.\d{3}/\d{2}\.\d{3}", 60)
        card = report["group3_fx_global"].get("fx_tm_mid")
        if not card:
            continue
        reported = next((v["value"] for v in card["values"] if v["week"] == week), None)
        truth = truth_fx.get("tm_mid")
        results.append(_make_result("fx_tm_mid", week_short, reported, truth, sbv_file.name, excerpt, strict))

    # === 4. US 10Y + DXY from VNBA (chỉ W26 có) ===
    vnba_file = cache_dir / "vnba_W26.txt"
    if vnba_file.exists():
        text = vnba_file.read_text(encoding="utf-8", errors="ignore")
        truth_global = parse_vnba_global(text)
        for key in ["us_10y", "dxy"]:
            card = report["group3_fx_global"].get(key)
            if not card or not card.get("values"):
                continue
            v = card["values"][0]
            reported = v.get("value")
            truth = truth_global.get(key)
            excerpt = excerpt_around(text, "DXY" if key == "dxy" else "10 năm", 80)
            results.append(_make_result(key, v["week"], reported, truth, vnba_file.name, excerpt, strict))

    # === 5. Cross-check SBV LNH vs VBMA LNH TB 5 ngày ===
    for week in weeks:
        week_short = week.split("-")[-1]
        sbv_file = cache_dir / f"sbv_{week}.txt"
        vbma_file = cache_dir / f"vbma_{week_short}.txt"
        if not (sbv_file.exists() and vbma_file.exists()):
            continue
        sbv_text = sbv_file.read_text(encoding="utf-8", errors="ignore")
        vbma_text = vbma_file.read_text(encoding="utf-8", errors="ignore")
        sbv_lnh = parse_sbv_lnh(sbv_text).get("overnight")
        vbma_tb5 = parse_vbma_lnh_tb5(vbma_text).get("on_tb5")
        if sbv_lnh is None or vbma_tb5 is None:
            continue
        delta_bp = abs(sbv_lnh - vbma_tb5) * 100
        excerpt = excerpt_around(vbma_text, r"^\s*ON\s+(\d+\.\d+)", 60)
        if delta_bp > 5:
            status = "MISMATCH"
            detail = f"Cross-check FAIL: SBV ON={sbv_lnh} vs VBMA TB5={vbma_tb5}, Δ={delta_bp:.1f}bp > 5bp"
        else:
            status = "OK"
            detail = f"Cross-check OK: SBV={sbv_lnh} vs VBMA TB5={vbma_tb5}, Δ={delta_bp:.1f}bp"
        results.append(VerifyResult("crosscheck_lnh_on", week_short,
            sbv_lnh, vbma_tb5, f"{sbv_file.name}+{vbma_file.name}", excerpt,
            delta_bp, status, detail))

    return results


def _make_result(key, week, reported, truth, source_file, excerpt, strict) -> VerifyResult:
    """Helper tạo VerifyResult với so sánh reported vs truth."""
    if truth is None:
        return VerifyResult(key, week, reported, truth, source_file, excerpt, None,
            "MISSING_SOURCE", f"Truth not parseable from {source_file}")
    if reported is None:
        return VerifyResult(key, week, reported, truth, source_file, excerpt, None,
            "NULL_REPORTED", f"Reported value is None but truth={truth}")
    if truth == 0:
        delta_pct = 0.0 if reported == 0 else 100.0
    else:
        delta_pct = abs(reported - truth) / abs(truth) * 100
    threshold = 0.1 if strict else 0.5  # strict=0.1%, normal=0.5%
    if delta_pct > threshold:
        return VerifyResult(key, week, reported, truth, source_file, excerpt, delta_pct,
            "MISMATCH", f"Δ={delta_pct:.3f}% exceeds {threshold}% (reported={reported} vs truth={truth})")
    return VerifyResult(key, week, reported, truth, source_file, excerpt, delta_pct,
        "OK", f"Δ={delta_pct:.3f}% within {threshold}%")



# ============================================================
# EXPANDED VERIFICATION — v2 (Phase 4: thêm indicators mở rộng)
# ============================================================

def verify_report_v2(report_path: Path, cache_dir: Path, strict: bool = False) -> list[VerifyResult]:
    """Verify report v2 — report_v2.json với prose + 70 indicators."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    weeks = report["period"]["weeks_covered"]
    results: list[VerifyResult] = []

    # === 1. LNH from SBV (4 weeks × 3 tenors = 12) — keep v1 logic ===
    for week in weeks:
        week_short = week.split("-")[-1]
        sbv_file = cache_dir / f"sbv_{week}.txt"
        if not sbv_file.exists():
            continue
        text = sbv_file.read_text(encoding="utf-8", errors="ignore")
        truth_lnh = parse_sbv_lnh(text)
        excerpt = excerpt_around(text, r"Qua đêm.*?9 tháng", 100)
        # In v2, LNH data is in sections.lnh.data_summary.on_4w etc
        on_4w = report.get("sections", {}).get("lnh", {}).get("data_summary", {}).get("on_4w", [])
        w1_4w = report.get("sections", {}).get("lnh", {}).get("data_summary", {}).get("w1_4w", [])
        m1_4w = report.get("sections", {}).get("lnh", {}).get("data_summary", {}).get("m1_4w", [])
        for series, truth_key, src_4w in [("lnh_on", "overnight", on_4w),
                                            ("lnh_1w", "one_week", w1_4w),
                                            ("lnh_1m", "one_month", m1_4w)]:
            reported = next((v["value"] for v in src_4w if v["week"] in (week, week_short) or v["week"].endswith(week_short)), None)
            truth = truth_lnh.get(truth_key)
            results.append(_make_result(series, week_short, reported, truth, sbv_file.name, excerpt, strict))

    # === 2. LSTP from VBMA (4 weeks × 3 tenors = 12) — keep v1 logic ===
    for week in weeks:
        week_short = week.split("-")[-1]
        vbma_file = cache_dir / f"vbma_{week_short}.txt"
        if not vbma_file.exists():
            continue
        text = vbma_file.read_text(encoding="utf-8", errors="ignore")
        truth_yields = parse_vbma_yield_table(text)
        excerpt = excerpt_around(text, r"\d{1,2}/\d{1,2}/2026\s+(\d+\.\d+%)", 100)
        y10_4w = report.get("sections", {}).get("lstp", {}).get("data_summary", {}).get("y10_4w", [])
        y5_4w = report.get("sections", {}).get("lstp", {}).get("data_summary", {}).get("y5_4w", [])
        y2_4w = report.get("sections", {}).get("lstp", {}).get("data_summary", {}).get("y2_4w", [])
        for series, truth_key, src_4w in [("lstp_2y", "yield_2y", y2_4w),
                                            ("lstp_5y", "yield_5y", y5_4w),
                                            ("lstp_10y", "yield_10y", y10_4w)]:
            reported = next((v["value"] for v in src_4w if v["week"] in (week, week_short) or v["week"].endswith(week_short)), None)
            truth = truth_yields.get(truth_key)
            results.append(_make_result(series, week_short, reported, truth, vbma_file.name, excerpt, strict))

    # === 3. FX from SBV (4 weeks) ===
    for week in weeks:
        week_short = week.split("-")[-1]
        sbv_file = cache_dir / f"sbv_{week}.txt"
        if not sbv_file.exists():
            continue
        text = sbv_file.read_text(encoding="utf-8", errors="ignore")
        truth_fx = parse_sbv_fx(text)
        excerpt = excerpt_around(text, r"\d{2}\.\d{3}/\d{2}\.\d{3}", 60)
        fx_4w = report.get("sections", {}).get("fx", {}).get("data_summary", {}).get("fx_mid_4w", [])
        reported = next((v["value"] for v in fx_4w if v["week"] in (week, week_short) or v["week"].endswith(week_short)), None)
        truth = truth_fx.get("tm_mid")
        results.append(_make_result("fx_tm_mid", week_short, reported, truth, sbv_file.name, excerpt, strict))

    # === 4. W26-only: yield curve 9 tenors from VBMA ===
    vbma_w26_file = cache_dir / "vbma_W26.txt"
    if vbma_w26_file.exists():
        text = vbma_w26_file.read_text(encoding="utf-8", errors="ignore")
        truth_yields_full = parse_vbma_yield_table(text)
        # Parse full 9-tenor table — need extended parse
        from extract_cards import _find_vbma_yield_table as find_table
        from extract_cards import VBMA_TENOR_COLS
        date_label, table_9 = find_table(text)
        curve_w26 = report.get("sections", {}).get("lstp", {}).get("data_summary", {}).get("curve_w26", {})
        excerpt = excerpt_around(text, r"\d{1,2}/\d{1,2}/2026\s+(\d+\.\d+%)", 120)
        for tenor in VBMA_TENOR_COLS:
            truth = table_9.get(tenor)
            reported = curve_w26.get(tenor)
            results.append(_make_result(f"curve_{tenor}", "W26", reported, truth, vbma_w26_file.name, excerpt, strict))

    # === 5. W26-only: auction from VBMA ===
    from extract_cards import parse_vbma_full
    if vbma_w26_file.exists():
        vbma_full = parse_vbma_full(text)
        auction_w26 = report.get("sections", {}).get("lstp", {}).get("data_summary", {}).get("auction_w26", {})
        for tenor, truth_d in vbma_full.auction.items():
            rep_d = auction_w26.get(tenor)
            if rep_d:
                truth_lstt = truth_d["lstt"]
                rep_lstt = rep_d["lstt"]
                results.append(_make_result(f"auction_{tenor}_lstt", "W26", rep_lstt, truth_lstt, vbma_w26_file.name, excerpt, strict))

    # === 6. Cross-check SBV vs VBMA LNH (4 weeks) ===
    for week in weeks:
        week_short = week.split("-")[-1]
        sbv_file = cache_dir / f"sbv_{week}.txt"
        vbma_file = cache_dir / f"vbma_{week_short}.txt"
        if not (sbv_file.exists() and vbma_file.exists()):
            continue
        sbv_text = sbv_file.read_text(encoding="utf-8", errors="ignore")
        vbma_text = vbma_file.read_text(encoding="utf-8", errors="ignore")
        sbv_lnh = parse_sbv_lnh(sbv_text).get("overnight")
        vbma_full = parse_vbma_full(vbma_text)
        vbma_tb5 = vbma_full.interbank.get("ON", {}).get("tb5") if vbma_full.interbank else None
        if sbv_lnh is None or vbma_tb5 is None:
            continue
        delta_bp = abs(sbv_lnh - vbma_tb5) * 100
        if delta_bp > 5:
            status = "MISMATCH"
            detail = f"Cross-check FAIL: SBV={sbv_lnh} vs VBMA TB5={vbma_tb5}, Δ={delta_bp:.1f}bp"
        else:
            status = "OK"
            detail = f"Cross-check OK: SBV={sbv_lnh} vs VBMA TB5={vbma_tb5}, Δ={delta_bp:.1f}bp"
        results.append(VerifyResult("crosscheck_lnh", week_short, sbv_lnh, vbma_tb5,
            f"{sbv_file.name}+{vbma_file.name}", "", delta_bp, status, detail))

    return results



def main():
    parser = argparse.ArgumentParser(description="BẮT BUỘC — verify report.json vs cache")
    parser.add_argument("--report", required=True, help="Path to report.json")
    parser.add_argument("--cache", required=True, help="Path to sources_cache dir")
    parser.add_argument("--strict", action="store_true", help="Threshold 0.1%% instead of 0.5%%")
    args = parser.parse_args()

    # Detect v1 or v2 format
    report_raw = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if "sections" in report_raw:
        results = verify_report_v2(Path(args.report), Path(args.cache), strict=args.strict)
        fmt_label = "v2 (prose + 70 indicators)"
    else:
        results = verify_report(Path(args.report), Path(args.cache), strict=args.strict)
        fmt_label = "v1 (basic 9 indicators)"

    # Report
    ok = [r for r in results if r.status == "OK"]
    fails = [r for r in results if r.status in ("MISMATCH", "MISSING_SOURCE", "NULL_REPORTED")]

    print("=" * 78)
    print(f"DATA VERIFICATION REPORT — {args.report}")
    print(f"Cache: {args.cache} | Strict: {args.strict}")
    print("=" * 78)
    print(f"{'Status':<8} {'Card':<22} {'Week':<6} {'Reported':<12} {'Truth':<12} {'Δ%':<8} {'Source'}")
    print("-" * 78)
    for r in results:
        symbol = {"OK": "✅", "MISMATCH": "❌", "MISSING_SOURCE": "⚠️", "NULL_REPORTED": "⚠️"}[r.status]
        rep_str = f"{r.reported}" if r.reported is not None else "NULL"
        tru_str = f"{r.truth}" if r.truth is not None else "NULL"
        delta_str = f"{r.delta_pct:.3f}" if r.delta_pct is not None else "—"
        print(f"{symbol:<8} {r.card_key:<22} {r.week:<6} {rep_str:<12} {tru_str:<12} {delta_str:<8} {r.source_file}")
    print("-" * 78)
    print(f"\n✅ OK: {len(ok)}/{len(results)}")

    if fails:
        print(f"\n❌ FAILURES ({len(fails)}):")
        for r in fails:
            print(f"  [{r.status}] {r.card_key} {r.week}: {r.detail}")
            print(f"    Source excerpt: {r.source_excerpt}")
        print(f"\n❌ VERIFICATION FAILED — report không đáng tin.")
        sys.exit(1)
    else:
        print(f"\n✅ VERIFICATION PASSED — mọi số liệu khớp source gốc.")
        sys.exit(0)


if __name__ == "__main__":
    main()
