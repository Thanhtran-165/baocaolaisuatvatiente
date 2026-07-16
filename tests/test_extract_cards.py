"""Tests for extract_cards.py — VBMA/SBV/VNBA PDF text parsers + cross-source resolve."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract_cards import (
    parse_vbma_yields, ParsedYield,
    parse_sbv_interbank, parse_vnba_global, parse_vnba_vn,
    ParsedInterbank, ParsedGlobal, ParsedVN, resolve_cross_source,
)


def test_parse_vbma_yields_finds_2y_5y_10y():
    """VBMA weekly text must yield 2Y/5Y/10Y govt bond rates.

    VBMA uses table 'BIẾN ĐỘNG LỢI SUẤT PHÒNG GIAO DỊCH VBMA' with columns
    1N/2N/3N/5N/7N/10N/15N/20N/30N and a row labeled with the latest Friday date.
    """
    fixture = Path(__file__).parent / "fixtures" / "vbma_sample.txt"
    text = fixture.read_text(encoding="utf-8")
    result = parse_vbma_yields(text)
    assert isinstance(result, ParsedYield)
    assert result.yield_2y is not None
    assert result.yield_5y is not None
    assert result.yield_10y is not None
    # Reasonable ranges for VN govt yields (percent) — 2026 yields ~3-5%
    for v in (result.yield_2y, result.yield_5y, result.yield_10y):
        assert 0.5 < v < 8.0, f"yield {v}% outside plausible range"
    # 10Y should typically be ≥ 2Y (normal curve)
    assert result.yield_10y >= result.yield_2y - 0.5  # allow slight inversion
    # Latest Friday row in fixture: 26/6/2026 → 2N=3.48, 5N=4.19, 10N=4.40
    assert abs(result.yield_2y - 3.48) < 0.01
    assert abs(result.yield_5y - 4.19) < 0.01
    assert abs(result.yield_10y - 4.40) < 0.01


def test_parse_vbma_yields_captures_source_week():
    """Parser should detect the report week from the latest date row."""
    fixture = Path(__file__).parent / "fixtures" / "vbma_sample.txt"
    text = fixture.read_text(encoding="utf-8")
    result = parse_vbma_yields(text)
    assert result.source_week is not None
    # Fixture is W26 2026 (week of 22-26/6/2026)
    assert "W26" in result.source_week or "2026" in result.source_week


def test_parse_vbma_yields_returns_none_on_garbage():
    result = parse_vbma_yields("this is not a VBMA report")
    assert result.yield_2y is None
    assert result.yield_5y is None
    assert result.yield_10y is None


def test_parse_sbv_interbank_finds_overnight_and_fx():
    fixture = Path(__file__).parent / "fixtures" / "sbv_sample.txt"
    text = fixture.read_text(encoding="utf-8")
    result = parse_sbv_interbank(text)
    assert isinstance(result, ParsedInterbank)
    assert result.overnight is not None
    assert 0.5 < result.overnight < 5.0  # plausible ON rate
    assert abs(result.overnight - 1.20) < 0.001
    assert result.fx_central is not None
    assert 20000 < result.fx_central < 30000  # plausible VND/USD
    assert abs(result.fx_central - 25140) < 1
    assert result.omo_net is not None  # +5000 (drain) or -5000 (inject)
    assert result.omo_net == 5000  # drain (hut tien = +)


def test_parse_vnba_global_finds_us10y_dxy_gold():
    fixture = Path(__file__).parent / "fixtures" / "vnba_sample.txt"
    text = fixture.read_text(encoding="utf-8")
    result = parse_vnba_global(text)
    assert isinstance(result, ParsedGlobal)
    assert result.us_10y is not None
    assert 3.0 < result.us_10y < 6.0
    assert abs(result.us_10y - 4.37) < 0.01
    assert result.dxy is not None
    assert 90 < result.dxy < 120
    assert abs(result.dxy - 101.357) < 0.1
    assert result.gold is not None
    assert 1500 < result.gold < 5000
    assert abs(result.gold - 4087.01) < 1
    assert result.brent is not None
    assert abs(result.brent - 71.99) < 0.1


def test_parse_vnba_vn_finds_vnindex_liquidity_foreignflow():
    fixture = Path(__file__).parent / "fixtures" / "vnba_sample.txt"
    text = fixture.read_text(encoding="utf-8")
    result = parse_vnba_vn(text)
    assert isinstance(result, ParsedVN)
    assert result.vnindex is not None
    assert 800 < result.vnindex < 2000
    assert abs(result.vnindex - 1285) < 1
    assert result.hose_liquidity_b_vnd is not None
    assert 5000 < result.hose_liquidity_b_vnd < 50000
    # Foreign flow: "Bán ròng 450 tỷ" → -450 (net sell)
    assert result.foreign_flow_b_vnd is not None
    assert result.foreign_flow_b_vnd == -450
    assert result.cpi_yoy is not None
    assert abs(result.cpi_yoy - 4.6) < 0.1


def test_resolve_cross_source_picks_sbv_when_divergent():
    """If SBV and VBMA disagree >5% on interbank, use SBV."""
    resolved = resolve_cross_source(
        sbv_overnight=1.20,
        vbma_overnight=1.55,  # ~29% divergence
    )
    assert abs(resolved.value - 1.20) < 0.001  # SBV wins
    assert resolved._conflict_flagged is True
    assert resolved.source == "SBV"


def test_resolve_cross_source_averages_when_close():
    resolved = resolve_cross_source(
        sbv_overnight=1.20,
        vbma_overnight=1.22,  # ~1.6% divergence
    )
    assert abs(resolved.value - 1.21) < 0.01  # averaged
    assert resolved._conflict_flagged is False


def test_resolve_cross_source_handles_one_none():
    resolved = resolve_cross_source(sbv_overnight=1.20, vbma_overnight=None)
    assert abs(resolved.value - 1.20) < 0.001
    assert resolved.source == "SBV"


# === TESTS CHO verify_data.py ===
import json
import tempfile
from verify_data import (
    parse_sbv_lnh as v_parse_sbv_lnh,
    parse_sbv_fx as v_parse_sbv_fx,
    parse_vbma_yield_table as v_parse_vbma_yield_table,
    parse_vnba_global as v_parse_vnba_global,
    parse_vbma_lnh_tb5, verify_report, _make_result
)


def test_verify_parse_sbv_lnh_real_format():
    """parse_sbv_lnh phải đọc đúng format SBV thật."""
    text = """2.2. Về lãi suất bình quân
           Qua đêm     1 tuần     2 tuần   1 tháng   3 tháng 6 tháng     9 tháng
  VND        6,81       6,59      6,73      7,01      7,61      8,13      6,65
  USD        3,63       3,67      3,69      3,77      3,99      4,20        -
"""
    result = v_parse_sbv_lnh(text)
    assert result["overnight"] == 6.81
    assert result["one_week"] == 6.59
    assert result["one_month"] == 7.01


def test_verify_parse_sbv_fx_last_pair():
    """parse_sbv_fx lấy cặp cuối cùng."""
    text = """Ngày 22/06 ở mức 26.122/26.442
Cuối ngày 26/06 ở mức 26.114/26.454"""
    result = v_parse_sbv_fx(text)
    assert result["tm_low"] == 26114
    assert result["tm_high"] == 26454
    assert result["tm_mid"] == 26284


def test_verify_parse_vbma_yield_table_9_cols():
    """parse_vbma_yield_table map đúng cột 2N=idx1, 5N=idx3, 10N=idx5."""
    text = """BIẾN ĐỘNG LỢI SUẤT
26/6/2026  3.38%  3.48%  3.56%  4.19%  4.25%  4.40%  4.57%  4.62%  4.69%
19/6/2026  3.37%  3.46%  3.55%  4.17%  4.21%  4.37%  4.55%  4.61%  4.68%
"""
    result = v_parse_vbma_yield_table(text)
    assert result["yield_2y"] == 3.48
    assert result["yield_5y"] == 4.19
    assert result["yield_10y"] == 4.40
    assert result["date_label"] == "26/6/2026"


def test_verify_parse_vnba_global_real_pattern():
    """parse_vnba_global đọc đúng 'về mức 4,37%' và 'DXY 101.357'."""
    text = """10 năm đóng cửa tuần giảm 7 điểm cơ bản về mức 4,37%
DXY              101.357     0.50%       2.17%"""
    result = v_parse_vnba_global(text)
    assert result["us_10y"] == 4.37
    assert result["dxy"] == 101.357


def test_verify_parse_vbma_lnh_tb5():
    """parse_vbma_lnh_tb5 đọc 'ON 4.25 2.91 4.41'."""
    text = """ON    4.25    2.91    4.41    -150    -477
1W    7.22    7.35    5.30    205    -13"""
    result = parse_vbma_lnh_tb5(text)
    assert result["on_tb5"] == 4.25
    assert result["on_close"] == 2.91


def test_verify_make_result_ok():
    """_make_result trả OK khi Δ < threshold."""
    r = _make_result("test", "W26", 4.26, 4.26, "sbv.txt", "context", strict=False)
    assert r.status == "OK"
    assert r.delta_pct == 0.0


def test_verify_make_result_mismatch():
    """_make_result trả MISMATCH khi Δ > threshold."""
    r = _make_result("test", "W26", 4.50, 4.26, "sbv.txt", "context", strict=False)
    assert r.status == "MISMATCH"
    assert r.delta_pct > 0.5


def test_verify_make_result_null_reported():
    r = _make_result("test", "W26", None, 4.26, "sbv.txt", "context", strict=False)
    assert r.status == "NULL_REPORTED"


def test_verify_make_result_strict_mode():
    """strict=True → threshold 0.1% thay vì 0.5%."""
    # Δ=0.2% — pass normal, fail strict
    r_normal = _make_result("t", "W26", 4.27, 4.26, "f", "c", strict=False)
    r_strict = _make_result("t", "W26", 4.27, 4.26, "f", "c", strict=True)
    assert r_normal.status == "OK"  # 0.2% < 0.5%
    assert r_strict.status == "MISMATCH"  # 0.2% > 0.1%


def test_verify_report_end_to_end_pass(tmp_path):
    """verify_report chạy end-to-end với synthetic data khớp."""
    # Tạo cache giả
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "sbv_2026-W26.txt").write_text(
        "Qua đêm     1 tuần     2 tuần   1 tháng   3 tháng 6 tháng     9 tháng\n"
        "  VND        4,26       7,34      7,76     7,32      7,94    8,12      8,06\n"
        "Cuối ngày 26/06 ở mức 26.114/26.454",
        encoding="utf-8",
    )
    (cache / "vbma_W26.txt").write_text(
        "26/6/2026  3.38%  3.48%  3.56%  4.19%  4.25%  4.40%  4.57%  4.62%  4.69%\n",
        encoding="utf-8",
    )
    # Tạo report.json khớp
    report = {
        "report_id": "test",
        "period": {"weeks_covered": ["2026-W26"]},
        "group1_money_market": {
            "interbank_on": {"values": [{"week": "2026-W26", "value": 4.26}]},
            "interbank_1w": {"values": [{"week": "2026-W26", "value": 7.34}]},
            "interbank_1m": {"values": [{"week": "2026-W26", "value": 7.32}]},
        },
        "group2_bonds": {
            "gov_2y_yield": {"values": [{"week": "2026-W26", "value": 3.48}]},
            "gov_5y_yield": {"values": [{"week": "2026-W26", "value": 4.19}]},
            "gov_10y_yield": {"values": [{"week": "2026-W26", "value": 4.40}]},
        },
        "group3_fx_global": {
            "fx_tm_mid": {"values": [{"week": "2026-W26", "value": 26284.0}]},
        },
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    results = verify_report(report_path, cache, strict=False)
    fails = [r for r in results if r.status in ("MISMATCH", "NULL_REPORTED")]
    assert not fails, f"Expected all OK, got failures: {[(r.card_key, r.status, r.detail) for r in fails]}"


def test_verify_report_detects_mismatch(tmp_path):
    """verify_report PHẢI phát hiện mismatch khi report.json sai số."""
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "sbv_2026-W26.txt").write_text(
        "Qua đêm     1 tuần     2 tuần   1 tháng   3 tháng 6 tháng     9 tháng\n"
        "  VND        4,26       7,34      7,76     7,32      7,94    8,12      8,06",
        encoding="utf-8",
    )
    # Report SAI: ON=5.00 thay vì 4.26
    report = {
        "period": {"weeks_covered": ["2026-W26"]},
        "group1_money_market": {
            "interbank_on": {"values": [{"week": "2026-W26", "value": 5.00}]},
            "interbank_1w": {"values": [{"week": "2026-W26", "value": 7.34}]},
            "interbank_1m": {"values": [{"week": "2026-W26", "value": 7.32}]},
        },
        "group2_bonds": {}, "group3_fx_global": {},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    results = verify_report(report_path, cache, strict=False)
    on_result = [r for r in results if r.card_key == "interbank_on"]
    assert on_result, "interbank_on not verified"
    assert on_result[0].status == "MISMATCH"
    assert "17.37" in on_result[0].detail  # Δ% ~= 17%
