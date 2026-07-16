"""build_report_v2.py — Build report.json with PROSE + 70 indicators (Phase 2).

Khác biệt v1:
  - Extract 70 indicators (LNH 7+7, yield 9, auction, FX 6, CB 6, govy 10Y 8, equities 9, bank PBT 10)
  - GENERATE PROSE per chủ đề (LNH/LSTP/FX/Global) dựa trên data thật
  - 4-week values[] cho LNH + yield curve (để trend)
  - Tuân thủ nguyên tắc "người kể chuyện số liệu, KHÔNG người cho ý kiến"

Usage:
  python3 build_report_v2.py --cache sources_cache/ --week 2026-W26 --out report.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_cards import (
    parse_vbma_full, parse_vnba_full,
)
from build_report import parse_sbv_interbank_real


def fmt_pct(v, sign=True):
    """Format percent với sign."""
    if v is None:
        return "—"
    s = "+" if (sign and v >= 0) else ""
    return f"{s}{v:.2f}%"


def fmt_bp(v):
    """Format basis points."""
    if v is None:
        return "—"
    s = "+" if v >= 0 else ""
    return f"{s}{v:.0f}bp"


def fmt_vnd(v):
    """Format VND amount."""
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f} triệu tỷ"
    if v >= 1_000:
        return f"{v/1_000:.1f} nghìn tỷ"
    return f"{v:.0f} tỷ"


def generate_lnh_prose(sbv_data_4w: list[dict], vbma_data: dict, target_week: str = "2026-W26") -> dict:
    """Generate prose cho section Liên ngân hàng.

    sbv_data_4w: list of parse_sbv_interbank_real results for 4 weeks
    vbma_data: parse_vbma_full for latest week
    """
    # Derive week labels from target_week parameter
    from datetime import date as _date
    _year, _week = int(target_week.split("-")[0]), int(target_week.split("-W")[1])
    weeks = []
    for _w in range(_week - 3, _week + 1):
        if _w < 1:
            _py = _year - 1
            _lw = _date(_py, 12, 28).isocalendar()[1]
            weeks.append(f"W{_lw + _w:02d}")
        else:
            weeks.append(f"W{_w:02d}")
    on_values = [d.get("overnight") for d in sbv_data_4w]
    w1_values = [d.get("one_week") for d in sbv_data_4w]
    m1_values = [d.get("one_month") for d in sbv_data_4w]

    # === Tóm tắt xu hướng (trend) ===
    on_now, on_then = on_values[-1], on_values[0]
    on_delta = on_now - on_then if (on_now and on_then) else None
    on_dir = "giảm" if (on_delta and on_delta < 0) else "tăng" if on_delta else "đi ngang"

    # === Phân tích chi tiết ===
    overview = (
        f"Trong 4 tuần trong 4 tuần qua, lãi suất liên ngân hàng (LNH) qua đêm (VND) {on_dir} "
        f"từ {on_then}% xuống {on_now}% — biến động {fmt_bp(on_delta*100 if on_delta else 0)} "
        f"trong kỳ. Đây là tín hiệu {('dovish — NHNN duy trì thanh khoản dồi dào' if on_delta and on_delta < 0 else 'hawkish nhẹ — thanh khoản căng hơn')}."
    )

    # === Tuần cuối chi tiết (VBMA có close + WoW bp) ===
    on_vbma = vbma_data.interbank.get("ON", {})
    w26_detail = ""
    if on_vbma:
        close = on_vbma.get("close")
        tb5 = on_vbma.get("tb5")
        wow_bp = on_vbma.get("wow_bp")
        mom_bp = on_vbma.get("mom_bp")
        w26_detail = (
            f"Theo VBMA, LNH ON ngày 26/6 đóng cửa ở mức {close}% (bình quân 5 ngày {tb5}%), "
            f"{fmt_bp(wow_bp)} so với tuần trước và {fmt_bp(mom_bp)} so với tháng trước. "
            f"Lãi suất kỳ hạn 1 tuần dao động mạnh: kỳ hạn cuối đạt {w1_values[-1]}%, "
            f"{'tăng vọt' if w1_values[-1] and w1_values[-2] and w1_values[-1] > w1_values[-2] * 1.1 else 'ổn định'} "
            f"so với tuần trước ({w1_values[-2]}%)."
        )

    # === Doanh số giao dịch (cần từ VBMA) ===
    volume_note = ""
    if vbma_data.omo_outstanding:
        volume_note = f"Thanh khoản thị trường: OMO lưu hành {fmt_vnd(vbma_data.omo_outstanding * 1000)}."

    return {
        "title": "Thị trường Liên ngân hàng (VND)",
        "overview": overview,
        "w26_detail": w26_detail,
        "volume_note": volume_note,
        "data_summary": {
            "on_4w": [{"week": w, "value": v} for w, v in zip(weeks, on_values)],
            "w1_4w": [{"week": w, "value": v} for w, v in zip(weeks, w1_values)],
            "m1_4w": [{"week": w, "value": v} for w, v in zip(weeks, m1_values)],
        },
    }


def generate_lstp_prose(vbma_4w: list, vnba: dict, target_week: str = '2026-W26') -> dict:
    """Generate prose cho section LSTP — yield curve + auction + secondary."""
    from datetime import date as _date
    _y, _w = int(target_week.split("-")[0]), int(target_week.split("-W")[1])
    weeks = [f"W{w:02d}" for w in range(max(1,_w-3), _w+1)]
    y10_values = [v.yields.get("10N") for v in vbma_4w]
    y5_values = [v.yields.get("5N") for v in vbma_4w]
    y2_values = [v.yields.get("2N") for v in vbma_4w]

    # Yield curve trend
    y10_now, y10_then = y10_values[-1], y10_values[0]
    y10_delta_bp = (y10_now - y10_then) * 100 if (y10_now and y10_then) else None
    curve_dir = "dịch lên" if (y10_delta_bp and y10_delta_bp > 0) else "dịch xuống"

    # Slope 10Y-2Y
    slope_now = (y10_values[-1] - y2_values[-1]) * 100 if (y10_values[-1] and y2_values[-1]) else None
    slope_then = (y10_values[0] - y2_values[0]) * 100 if (y10_values[0] and y2_values[0]) else None

    overview = (
        f"Đường cong lợi suất trái phiếu Chính phủ (TPCP) {curve_dir} đều toàn kỳ hạn trong 4 tuần. "
        f"LSTP 10 năm tăng từ {y10_then}% (đầu kỳ) lên {y10_now}% (cuối kỳ) — {fmt_bp(y10_delta_bp)} trong kỳ. "
    )
    if slope_now is not None and slope_then is not None:
        overview += (
            f"Slope 10Y-2Y ở mức {slope_now:.0f}bp ({'mở rộng' if slope_now > slope_then else 'thu hẹp'} "
            f"từ {slope_then:.0f}bp), cho thấy curve vẫn bình thường — không inversion."
        )
    else:
        overview += "Curve giữ hình thái bình thường."

    # W26 chi tiết — toàn bộ yield curve
    vbma_w26 = vbma_4w[-1]
    w26_curve = ", ".join([f"{t}={v}%" for t, v in vbma_w26.yields.items()])
    w26_wow = ", ".join([f"{t} {fmt_bp(bp)}" for t, bp in list(vbma_w26.yields_wow_bp.items())[:5]])

    w26_detail = f"Tuần cuối curve: {w26_curve}. WoW (bp): {w26_wow}..."

    # Đấu thầu
    auction_text = ""
    if vbma_w26.auction:
        auction_parts = []
        for tenor, d in vbma_w26.auction.items():
            ratio = (d["gttt"] / d["gtgt"] * 100) if d["gtgt"] else 0
            auction_parts.append(f"{tenor} {ratio:.0f}% ({d['gttt']:.0f}/{d['gtgt']:.0f} tỷ, LSTT {d['lstt']}%)")
        auction_text = f"Phiên đấu thầu 24/6: tỷ lệ trúng thầu — {', '.join(auction_parts)}."

    # Secondary
    secondary_text = ""
    if vbma_w26.secondary_total:
        secondary_text = (
            f"Giao dịch thứ cấp đạt {vbma_w26.secondary_total:,.0f} tỷ VND. "
            f"Foreign: bán ròng {vbma_w26.foreign_net_sell_week:.0f} tỷ tuần, "
            f"lũy kế YTD {vbma_w26.foreign_net_sell_ytd:,.0f} tỷ."
        )

    return {
        "title": "Thị trường Trái phiếu Chính phủ",
        "overview": overview,
        "w26_detail": w26_detail,
        "auction_text": auction_text,
        "secondary_text": secondary_text,
        "data_summary": {
            "y10_4w": [{"week": w, "value": v} for w, v in zip(weeks, y10_values)],
            "y5_4w": [{"week": w, "value": v} for w, v in zip(weeks, y5_values)],
            "y2_4w": [{"week": w, "value": v} for w, v in zip(weeks, y2_values)],
            "curve_w26": vbma_w26.yields,
            "curve_wow_bp": vbma_w26.yields_wow_bp,
            "auction_w26": vbma_w26.auction,
        },
    }


def generate_fx_prose(sbv_4w: list, vbma_w26, vnba_w26, target_week: str = '2026-W26') -> dict:
    """Generate prose cho section Ngoại hối."""
    from datetime import date as _date
    _y, _w = int(target_week.split("-")[0]), int(target_week.split("-W")[1])
    weeks = [f"W{w:02d}" for w in range(max(1,_w-3), _w+1)]
    fx_values = []
    for d in sbv_4w:
        if d.get("fx_tm_low") and d.get("fx_tm_high"):
            fx_values.append((d["fx_tm_low"] + d["fx_tm_high"]) / 2)
        else:
            fx_values.append(None)

    fx_now, fx_then = fx_values[-1], fx_values[0]
    fx_delta = fx_now - fx_then if (fx_now and fx_then) else None
    fx_pct = (fx_delta / fx_then * 100) if (fx_delta and fx_then) else None

    # DXY
    dxy = vnba_w26.fx.get("DXY") if vnba_w26 else None

    overview_parts = []
    if fx_now is not None and fx_then is not None:
        overview_parts.append(
            f"Tỷ giá USD/VND (TM, mid) dao động: {fx_then:,.0f} → {fx_now:,.0f}"
            + (f", biến động {fx_pct:+.2f}% trong 4 tuần." if fx_pct is not None else ".")
        )
    else:
        overview_parts.append("Tỷ giá USD/VND ổn định.")
    if dxy:
        overview_parts.append(f"DXY ở mức {dxy}.")
    overview = " ".join(overview_parts)

    # VBMA FX pairs
    pairs_text = ""
    if vbma_w26 and vbma_w26.fx_pairs:
        pairs = []
        for pair, d in list(vbma_w26.fx_pairs.items())[:4]:
            pairs.append(f"{pair} {d['rate']:,.3f} ({fmt_pct(d['wow_pct'])} WoW)")
        pairs_text = f"Các cặp tiền chính: {', '.join(pairs)}."

    return {
        "title": "Thị trường Ngoại hối",
        "overview": overview,
        "pairs_text": pairs_text,
        "data_summary": {
            "fx_mid_4w": [{"week": w, "value": v} for w, v in zip(weeks, fx_values)],
            "fx_pairs_w26": vbma_w26.fx_pairs if vbma_w26 else {},
            "dxy": dxy,
        },
    }


def generate_global_prose(vnba_w26) -> dict:
    """Generate prose cho section Bối cảnh toàn cầu."""
    cb = vnba_w26.cb_rates if vnba_w26 else {}
    govy = vnba_w26.govy_10y if vnba_w26 else {}
    eq = vnba_w26.equities if vnba_w26 else {}
    comm = vnba_w26.commodities if vnba_w26 else {}

    cb_text = ""
    if cb:
        cb_parts = [f"{name} {d['current']}" for name, d in cb.items()]
        cb_text = f"Lãi suất chính sách: {', '.join(cb_parts)}."

    eq_text = ""
    if eq:
        eq_parts = []
        for name, d in list(eq.items())[:5]:
            wow = d.get("wow_pct", 0)
            emoji = "🟢" if wow > 0 else "🔴"
            eq_parts.append(f"{name} {fmt_pct(wow)}")
        eq_text = f"Chỉ số CK toàn cầu (WoW): {', '.join(eq_parts)}."

    govy_text = ""
    if govy:
        govy_parts = []
        for code, d in govy.items():
            govy_parts.append(f"{code} {d['yield']:.2f}%")
        govy_text = f"Lợi suất TPCP 10 năm: {', '.join(govy_parts)}."

    comm_text = ""
    if comm:
        comm_parts = [f"{k} {v:,.2f}" for k, v in comm.items()]
        comm_text = f"Hàng hóa: {', '.join(comm_parts)}."

    overview = f"Tuần báo cáo thị trường toàn cầu {('hồi phục nhẹ' if eq and any(d.get('wow_pct', 0) > 0 for d in eq.values()) else 'điều chỉnh')}. " + " ".join(filter(None, [cb_text, govy_text, eq_text, comm_text]))

    return {
        "title": "Bối cảnh Toàn cầu",
        "overview": overview,
        "cb_text": cb_text,
        "eq_text": eq_text,
        "govy_text": govy_text,
        "comm_text": comm_text,
        "data_summary": {
            "cb_rates": cb,
            "govy_10y": govy,
            "equities": eq,
            "commodities": comm,
        },
    }


def generate_vn_prose(vnba_w26) -> dict:
    """Generate prose cho section VN — bank PBT + VN gold + CPI."""
    bank_pbt = vnba_w26.bank_pbt if vnba_w26 else {}
    sjc_buy = vnba_w26.sjc_buy
    sjc_sell = vnba_w26.sjc_sell
    cpi_mom = vnba_w26.cpi_mom_expected
    cpi_avg = vnba_w26.cpi_avg_2026_expected

    bank_text = ""
    if bank_pbt:
        # Sort by YoY
        sorted_banks = sorted(bank_pbt.items(), key=lambda x: x[1]["yoy_pct"], reverse=True)
        top3 = sorted_banks[:3]
        bottom3 = sorted_banks[-3:]
        top_str = ", ".join([f"{t} {fmt_pct(d['yoy_pct'])}" for t, d in top3])
        bot_str = ", ".join([f"{t} {fmt_pct(d['yoy_pct'])}" for t, d in bottom3])
        bank_text = f"Lợi nhuận ngân hàng Q2/2026 (dự báo): Top tăng trưởng — {top_str}. Yếu nhất — {bot_str}."

    gold_text = ""
    if sjc_buy and sjc_sell:
        gold_text = f"Vàng SJC: {sjc_buy}–{sjc_sell} trđ/lượng."

    cpi_text = ""
    if cpi_mom or cpi_avg:
        parts = []
        if cpi_mom:
            parts.append(f"CPI 6/2026 kỳ vọng {cpi_mom}% MoM")
        if cpi_avg:
            parts.append(f"bình quân 2026 {cpi_avg}%")
        cpi_text = " — ".join(parts) + "."

    overview = " ".join(filter(None, [bank_text, gold_text, cpi_text]))

    return {
        "title": "Bối cảnh Việt Nam",
        "overview": overview,
        "bank_text": bank_text,
        "gold_text": gold_text,
        "cpi_text": cpi_text,
        "data_summary": {
            "bank_pbt": bank_pbt,
            "sjc": {"buy": sjc_buy, "sell": sjc_sell},
            "cpi": {"mom_expected": cpi_mom, "avg_2026_expected": cpi_avg},
        },
    }


def build_report_v2(cache_dir: Path, target_week: str) -> dict:
    """Build report v2 với prose + 70 indicators."""
    year_str, week_str = target_week.split("-W")
    year, week = int(year_str), int(week_str)
    weeks = [f"{year}-W{w:02d}" for w in range(week - 3, week + 1)]

    # Parse SBV 4 weeks
    sbv_4w = []
    for w in weeks:
        sbv_file = cache_dir / f"sbv_{w}.txt"
        if sbv_file.exists():
            text = sbv_file.read_text(encoding="utf-8", errors="ignore")
            sbv_4w.append(parse_sbv_interbank_real(text))
        else:
            sbv_4w.append({})

    # Parse VBMA 4 weeks
    vbma_4w = []
    for w in weeks:
        w_short = w.split("-")[-1]
        vbma_file = cache_dir / f"vbma_{w_short}.txt"
        if vbma_file.exists():
            text = vbma_file.read_text(encoding="utf-8", errors="ignore")
            vbma_4w.append(parse_vbma_full(text))
        else:
            vbma_4w.append(parse_vbma_full(""))

    vbma_w26 = vbma_4w[-1] if vbma_4w else None

    # Parse VNBA (latest available — try target week, then any vnba_*.txt)
    vnba_w26 = None
    target_week_short = target_week.split("-")[-1]  # e.g. "W26"
    vnba_file = cache_dir / f"vnba_{target_week_short}.txt"
    if not vnba_file.exists():
        # Fallback: find any vnba_*.txt
        vnba_files = sorted(cache_dir.glob("vnba_W*.txt"))
        if vnba_files:
            vnba_file = vnba_files[-1]  # most recent
    if vnba_file.exists():
        vnba_w26 = parse_vnba_full(vnba_file.read_text(encoding="utf-8", errors="ignore"))

    # Generate prose per chủ đề
    lnh_prose = generate_lnh_prose(sbv_4w, vbma_w26, target_week)
    lstp_prose = generate_lstp_prose(vbma_4w, vnba_w26, target_week)
    fx_prose = generate_fx_prose(sbv_4w, vbma_w26, vnba_w26, target_week)
    global_prose = generate_global_prose(vnba_w26)
    vn_prose = generate_vn_prose(vnba_w26)

    # Verdict
    on_values = [d.get("overnight") for d in sbv_4w]
    y10_values = [v.yields.get("10N") for v in vbma_4w]
    on_delta = (on_values[-1] - on_values[0]) if (on_values[-1] and on_values[0]) else 0
    y10_delta = (y10_values[-1] - y10_values[0]) if (y10_values[-1] and y10_values[0]) else 0
    stance_score = 0
    if on_delta < -0.5:
        stance_score += 2
    elif on_delta > 0.5:
        stance_score -= 2
    if y10_delta > 0.05:
        stance_score -= 1
    elif y10_delta < -0.05:
        stance_score += 1

    if stance_score >= 3:
        verdict, verdict_short = "THUẬN (dovish)", "THUẬN"
    elif stance_score >= 1:
        verdict, verdict_short = "LƯỢNG (mild dovish)", "LƯỢNG"
    elif stance_score <= -3:
        verdict, verdict_short = "THẮN CHẶT (hawkish)", "THẮN CHẶT"
    elif stance_score <= -1:
        verdict, verdict_short = "THẮN CHẶT NHẸ", "THẮN CHẶT NHẸ"
    else:
        verdict, verdict_short = "TRUNG TÍNH", "TRUNG TÍNH"

    verdict_reason = (
        f"LNH ON {on_delta:+.2f}pp ({'dovish' if on_delta < 0 else 'hawkish'}), "
        f"LSTP 10Y {y10_delta:+.2f}pp ({'dovish' if y10_delta < 0 else 'hawkish'}). "
        f"Stance score: {stance_score}/6."
    )

    # Compute cutoff date from target week's Friday
    from datetime import date as _date
    cutoff_date = _date.fromisocalendar(year, week, 5).isoformat()

    report = {
        "report_id": f"vn-rates-{target_week}",
        "period": {
            "week": week, "year": year,
            "data_cutoff": cutoff_date,
            "weeks_covered": weeks,
        },
        "verdict": verdict_short,
        "verdict_full": verdict,
        "verdict_reason": verdict_reason,
        "stance_score": stance_score,
        "sections": {
            "lnh": lnh_prose,
            "lstp": lstp_prose,
            "fx": fx_prose,
            "global": global_prose,
            "vn": vn_prose,
        },
        "_sources_coverage": {
            "available": ["SBV", "VBMA"],
            "partial": ["VNBA (tuần cuối)"],
            "user_override": True,
        },
        "_data_provenance": {
            "sources_files": {
                f"sbv_{w}.txt": ["LNH VND 7 kỳ hạn", "tỷ giá TM USD/VND"]
                for w in weeks
            },
            "vbma_files": {f"vbma_{w.split('-')[-1]}.txt": ["yield curve 9", "interbank 7", "auction", "FX 6 pairs"] for w in weeks},
            "vnba (tuần cuối)": ["CB rates", "10Y govy 8", "equities 9", "bank PBT 10", "commodities", "gold SJC"],
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = build_report_v2(Path(args.cache), args.week)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Built v2: {args.out}")
    print(f"Verdict: {report['verdict']} (stance {report['stance_score']})")
    sections = report["sections"]
    print(f"Sections: {list(sections.keys())}")
    for k, v in sections.items():
        overview_len = len(v.get("overview", ""))
        print(f"  {k}: overview={overview_len} chars")


if __name__ == "__main__":
    main()
