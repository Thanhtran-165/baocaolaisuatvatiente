"""extract_cards.py — Parse PDF text from SBV/VBMA/VNBA weekly reports.

Each parser returns a dataclass with the indicators it could extract.
Missing indicators are None (never fabricated).

VBMA format (confirmed from real 2026-W26 fixture):
  Section 'BIẾN ĐỘNG LỢI SUẤT PHÒNG GIAO DỊCH VBMA' has a table with
  columns 1N 2N 3N 5N 7N 10N 15N 20N 30N (N = năm).
  Latest row labeled with the Friday date (e.g. '26/6/2026').
  Values are percent like '3.48%'.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedYield:
    """Govt bond yields parsed from one weekly report."""
    yield_2y: Optional[float] = None
    yield_5y: Optional[float] = None
    yield_10y: Optional[float] = None
    source_week: Optional[str] = None  # "2026-W26" or "26/6/2026"


# Column order in VBMA 'BIẾN ĐỘNG LỢI SUẤT PHÒNG GIAO DỊCH VBMA' table
VBMA_TENOR_COLS = ["1N", "2N", "3N", "5N", "7N", "10N", "15N", "20N", "30N"]
# Map our ParsedYield fields to VBMA column indices
VBMA_FIELD_TO_COL = {"yield_2y": "2N", "yield_5y": "5N", "yield_10y": "10N"}


def _find_vbma_yield_table(text: str) -> tuple[Optional[str], dict[str, float]]:
    """Locate the VBMA yield table and return (latest_date, {tenor: value}).

    The data row format (confirmed from 2026-W26 fixture):
      "26/6/2026  3.38%  3.48%  3.56%  4.19%  4.25%  4.40%  4.57%  4.62%  4.69%"
    i.e. a date followed by exactly 9 percent values, matching the 9 tenor columns.
    The FIRST such row in the document is the latest week (top-down chronology).
    """
    # Match: date + exactly 9 percentage values on one line
    row_re = re.compile(
        r"^(\d{1,2}/\d{1,2}/\d{4})\s+"
        + r"\s+".join([r"(\d{1,2}\.\d{2,4})%"] * 9)
        + r"\s*$",
        re.MULTILINE,
    )
    m = row_re.search(text)
    if not m:
        return None, {}
    date_label = m.group(1)
    values = {}
    for i, tenor in enumerate(VBMA_TENOR_COLS):
        values[tenor] = float(m.group(2 + i))
    return date_label, values


def parse_vbma_yields(text: str) -> ParsedYield:
    """Parse VBMA weekly report text for govt bond yields 2Y/5Y/10Y.

    VBMA table 'BIẾN ĐỘNG LỢI SUẤT PHÒNG GIAO DỊCH VBMA' uses tenor labels
    1N/2N/3N/5N/7N/10N/15N/20N/30N (N = năm). The latest-week row has format
    "DD/M/YYYY  3.38%  3.48%  ...  4.69%" (date + 9 percentages).
    """
    result = ParsedYield()
    date_label, table = _find_vbma_yield_table(text)
    if not table:
        return result
    result.source_week = date_label
    result.yield_2y = table.get("2N")
    result.yield_5y = table.get("5N")
    result.yield_10y = table.get("10N")
    return result


@dataclass
class ParsedInterbank:
    """SBV weekly bulletin parsed fields."""
    overnight: Optional[float] = None
    one_week: Optional[float] = None
    two_week: Optional[float] = None
    one_month: Optional[float] = None
    fx_central: Optional[float] = None
    fx_tm_avg: Optional[float] = None
    omo_net: Optional[float] = None  # + = drain (hut), - = inject (bom) (tỷ VND)


@dataclass
class ParsedGlobal:
    """VNBA Part I — global macro."""
    us_10y: Optional[float] = None
    us_2y: Optional[float] = None
    dxy: Optional[float] = None
    gold: Optional[float] = None  # USD/oz
    brent: Optional[float] = None  # USD/bbl


@dataclass
class ParsedVN:
    """VNBA Part II — Vietnam market."""
    vnindex: Optional[float] = None
    hose_liquidity_b_vnd: Optional[float] = None
    foreign_flow_b_vnd: Optional[float] = None  # + = net buy, - = net sell
    cpi_yoy: Optional[float] = None


@dataclass
class ResolvedValue:
    value: float
    source: str
    _conflict_flagged: bool = False


def parse_sbv_interbank(text: str) -> ParsedInterbank:
    """Parse SBV weekly bulletin PDF text.

    Fixture format (confirmed):
      'Overnight 1.20'
      '1 tuần    1.45'
      'Tỷ giá trung tâm tham chiếu: 25.140'
      'hút tiền qua OMO: 5.000 tỷ' (drain = +)
    """
    r = ParsedInterbank()
    # Overnight — appears as 'Overnight <number>' or 'O/N <number>'
    m = re.search(r"Overnight\s+(\d{1,2}[.,]\d{1,4})", text, re.I)
    if m:
        r.overnight = float(m.group(1).replace(",", "."))
    # 1 tuần / 1 tuần] / 1W
    m = re.search(r"1 tuần\s+(\d{1,2}[.,]\d{1,4})", text, re.I)
    if m:
        r.one_week = float(m.group(1).replace(",", "."))
    m = re.search(r"2 tuần\s+(\d{1,2}[.,]\d{1,4})", text, re.I)
    if m:
        r.two_week = float(m.group(1).replace(",", "."))
    m = re.search(r"1 tháng\s+(\d{1,2}[.,]\d{1,4})", text, re.I)
    if m:
        r.one_month = float(m.group(1).replace(",", "."))
    # FX central — 'Tỷ giá trung tâm ... 25.140' (VN uses dot as thousands)
    m = re.search(r"tỷ giá trung tâm[^0-9]{0,40}(\d{1,2}[.,]\d{3})", text, re.I)
    if m:
        # '25.140' → 25140 (dot = thousands sep)
        r.fx_central = float(m.group(1).replace(".", "").replace(",", ""))
    # OMO — 'hut tien' (drain=+) or 'bom tien' (inject=-)
    m = re.search(r"hút tiền[^0-9]{0,30}(\d{1,3}[.,]\d{3})", text, re.I)
    if m:
        r.omo_net = float(m.group(1).replace(".", "").replace(",", ""))
    else:
        m = re.search(r"bơm tiền[^0-9]{0,30}(\d{1,3}[.,]\d{3})", text, re.I)
        if m:
            r.omo_net = -float(m.group(1).replace(".", "").replace(",", ""))
    return r


def parse_vnba_global(text: str) -> ParsedGlobal:
    """Parse VNBA Part I — global macro section.

    Real format (from 2026-W26):
      'Lợi suất ... 10 năm đóng cửa tuần giảm 7 điểm cơ bản về mức 4,37%'
      'DXY đóng cửa tuần giảm nhẹ về mức 101,4 điểm' OR table 'DXY  101.357'
      'Giá vàng giao ngay tăng 1,2% lên khoảng 4.087 USD/ounce'
      'giá dầu Brent giao tháng 8 giảm 4,34%, chốt phiên ở mức 71,99' (USD/thùng)
    """
    r = ParsedGlobal()
    # US 10Y — '10 năm ... về mức 4,37%'
    m = re.search(r"10 năm[^.]{0,80}về mức\s+(\d{1,2}[.,]\d{1,2})\s*%", text, re.I)
    if m:
        r.us_10y = float(m.group(1).replace(",", "."))
    # US 2Y
    m = re.search(r"2 năm[^.]{0,80}về mức\s+(\d{1,2}[.,]\d{1,2})\s*%", text, re.I)
    if m:
        r.us_2y = float(m.group(1).replace(",", "."))
    # DXY — prefer table 'DXY  101.357'
    m = re.search(r"DXY\s+(\d{2,3}[.,]\d{1,3})", text)
    if m:
        r.dxy = float(m.group(1).replace(",", "."))
    else:
        m = re.search(r"DXY[^.]{0,60}về mức\s+(\d{2,3}[.,]\d{1,2})", text, re.I)
        if m:
            r.dxy = float(m.group(1).replace(",", "."))
    # Gold — table 'Vàng USD/t.oz  4087.01'
    m = re.search(r"Vàng USD/t\.oz\s+(\d{3,5}[.,]\d{1,2})", text, re.I)
    if m:
        r.gold = float(m.group(1).replace(",", ""))
    else:
        m = re.search(r"vàng[^.]{0,40}(\d{1,2}[.,]\d{3})\s*USD", text, re.I)
        if m:
            r.gold = float(m.group(1).replace(".", "").replace(",", ""))
    # Brent — 'Brent ... ở mức 71,99'
    m = re.search(r"Brent[^.]{0,80}ở mức\s+(\d{2,3}[.,]\d{1,2})", text, re.I)
    if m:
        r.brent = float(m.group(1).replace(",", "."))
    return r


def parse_vnba_vn(text: str) -> ParsedVN:
    """Parse VNBA Part II — Vietnam market.

    Real format: search for VN-Index, HOSE liquidity, foreign flow, CPI.
    """
    r = ParsedVN()
    # VN-Index — handles VN thousands '1.285' or '1,285' or decimal '1285.32'
    m = re.search(r"VN-?Index[^.]{0,80}(?:đóng|chốt|mức)\s+(\d[\d.,]*\d|\d)", text, re.I)
    if m:
        val_str = m.group(1)
        # VN format: dot or comma as thousands sep ('1.285' = 1285)
        # If both . and , present: ',XX' is decimal (e.g. '1,285.32')
        if "." in val_str and "," in val_str:
            # '1,285.32' → 1285.32
            val_str = val_str.replace(",", "")
        elif "." in val_str:
            # '1.285' → could be 1.285 (decimal) or 1285 (thousands)
            # Heuristic: if 3 digits after dot AND no further dots → thousands
            parts = val_str.split(".")
            if len(parts) == 2 and len(parts[1]) == 3:
                val_str = val_str.replace(".", "")
            # else keep as decimal
        elif "," in val_str:
            parts = val_str.split(",")
            if len(parts) == 2 and len(parts[1]) == 3:
                val_str = val_str.replace(",", "")
            elif len(parts) == 2 and len(parts[1]) <= 2:
                val_str = val_str.replace(",", ".")
        r.vnindex = float(val_str)
    # HOSE liquidity — 'đạt 18.500 tỷ' (VN thousands)
    m = re.search(r"thanh khoản\s*(?:HOSE|thị trường HOSE|\bHOSE\b)[^\d]{0,20}đạt\s+(\d{1,3}[.,]\d{3})", text, re.I)
    if not m:
        m = re.search(r"thanh khoản\s*(?:HOSE|thị trường)\s*đạt\s+(\d{1,3}[.,]\d{3})", text, re.I)
    if m:
        r.hose_liquidity_b_vnd = float(m.group(1).replace(".", "").replace(",", ""))
    # Foreign flow — 'bán ròng 450 tỷ' or 'mua ròng 1.450 tỷ'
    m = re.search(r"(bán ròng|mua ròng)\s+(\d{1,3}(?:[.,]\d{3})*|\d+)\s*tỷ", text, re.I)
    if m:
        val_str = m.group(2)
        val = float(val_str.replace(".", "").replace(",", ""))
        r.foreign_flow_b_vnd = -val if m.group(1).lower() == "bán ròng" else val
    # CPI — 'CPI YoY tháng 6: 4.6%' — number may be preceded by month digit
    m = re.search(r"CPI[^%]{0,40}?(\d{1,2}[.,]\d{1,2})\s*%", text, re.I)
    if not m:
        m = re.search(r"lạm phát[^%]{0,40}?(\d{1,2}[.,]\d{1,2})\s*%", text, re.I)
    if m:
        r.cpi_yoy = float(m.group(1).replace(",", "."))
    return r


def resolve_cross_source(
    sbv_overnight: Optional[float],
    vbma_overnight: Optional[float],
    threshold_pct: float = 5.0,
) -> ResolvedValue:
    """Resolve interbank ON conflict between SBV and VBMA.

    Priority: SBV > VBMA (SBV is the official source).
    - Both None → raise ValueError
    - One None → return the other
    - Both present, divergence > threshold → use SBV, flag conflict
    - Both present, divergence <= threshold → average
    """
    if sbv_overnight is None and vbma_overnight is None:
        raise ValueError("Both sources None for interbank ON")
    if sbv_overnight is None:
        return ResolvedValue(vbma_overnight, source="VBMA")
    if vbma_overnight is None:
        return ResolvedValue(sbv_overnight, source="SBV")
    avg = (sbv_overnight + vbma_overnight) / 2
    divergence = abs(sbv_overnight - vbma_overnight) / avg * 100
    if divergence > threshold_pct:
        return ResolvedValue(sbv_overnight, source="SBV", _conflict_flagged=True)
    return ResolvedValue(avg, source="SBV+VBMA avg")


# ============================================================
# EXPANDED PARSERS — v2 (Phase 1: ~25 must-have indicators)
# ============================================================

@dataclass
class ParsedVBMAFull:
    """VBMA full extraction — yield curve 9 tenors + interbank 7 + auction 5 + secondary + foreign."""
    # Yield curve (L316-321, latest row 26/6/2026)
    yields: dict = field(default_factory=dict)  # {"1N": 3.38, "2N": 3.48, ..., "30N": 4.69}
    yields_wow_bp: dict = field(default_factory=dict)  # WoW bp per tenor
    yields_yoy_bp: dict = field(default_factory=dict)
    # Interbank (L113-120)
    interbank: dict = field(default_factory=dict)  # {"ON": {"tb5": 4.25, "close": 2.91, "wow_bp": -150, "mom_bp": -477}}
    # Auction (L246-251)
    auction: dict = field(default_factory=dict)  # {"3Y": {"gtgt": 500, "gtdt": 625, "gttt": 125, "lstt": 3.52, "delta_bp": 0}}
    # Secondary (L291-294)
    secondary_total: Optional[float] = None
    secondary_outright_avg_day: Optional[float] = None
    secondary_outright_wow_pct: Optional[float] = None
    secondary_repo_avg_day: Optional[float] = None
    secondary_repo_wow_pct: Optional[float] = None
    # Foreign (L296-297)
    foreign_net_sell_week: Optional[float] = None
    foreign_net_sell_ytd: Optional[float] = None
    # FX pairs (L216-223)
    fx_pairs: dict = field(default_factory=dict)  # {"USD/VND": {"rate": 26300, "wow_pct": -0.08, "ytd_pct": 8.12}}
    # OMO (L99-102)
    omo_offered: Optional[float] = None
    omo_won: Optional[float] = None
    omo_matured: Optional[float] = None
    omo_net: Optional[float] = None
    omo_outstanding: Optional[float] = None
    omo_rate: Optional[float] = None
    # TPDN (L353-378)
    tpdn_issues_month: Optional[int] = None
    tpdn_total_month: Optional[float] = None
    tpdn_ytd: Optional[float] = None
    tpdn_buyback_ytd: Optional[float] = None
    tpdn_due_rest_year: Optional[float] = None


def parse_vbma_full(text: str) -> ParsedVBMAFull:
    """Parse VBMA weekly report for ALL must-have indicators (Phase 1)."""
    r = ParsedVBMAFull()

    # 1. Yield curve 9 tenors (latest row: "26/6/2026  3.38%  3.48% ... 4.69%")
    row_re = re.compile(
        r"^(\d{1,2}/\d{1,2}/\d{4})\s+"
        + r"\s+".join([r"(\d{1,2}\.\d{2,4})%"] * 9)
        + r"\s*$", re.MULTILINE,
    )
    m = row_re.search(text)
    if m:
        tenors = ["1N", "2N", "3N", "5N", "7N", "10N", "15N", "20N", "30N"]
        for i, t in enumerate(tenors):
            r.yields[t] = float(m.group(2 + i))
        # WoW row (next: "WoW (đcb)  1.14  1.36 ...")
        after = text[m.end():m.end() + 1500]
        wow_re = re.compile(r"WoW[^0-9-]*([-\d.,\s]+)", re.I)
        wm = wow_re.search(after)
        if wm:
            nums = re.findall(r"-?[\d.,]+", wm.group(1))
            bp_vals = []
            for n in nums:
                try:
                    bp_vals.append(float(n.replace(",", ".")))
                except ValueError:
                    pass
            for i, t in enumerate(tenors):
                if i < len(bp_vals):
                    r.yields_wow_bp[t] = bp_vals[i]

    # 2. Interbank 7 tenors (L113-120) — "ON  4.25  2.91  4.41  -150  -477"
    ib_re = re.compile(
        r"^\s*(ON|1W|2W|1M|3M|6M|9M)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+)\s+(-?\d+)",
        re.MULTILINE,
    )
    for im in ib_re.finditer(text):
        tenor = im.group(1)
        r.interbank[tenor] = {
            "tb5": float(im.group(2)),
            "close": float(im.group(3)),
            "prev_close": float(im.group(4)),
            "wow_bp": float(im.group(5)),
            "mom_bp": float(im.group(6)),
        }

    # 3. Auction 5 tenors (L246-251) — "1  24/6/2026  KBNN  TD2629001  3  500  625  125  3.52  0"
    auc_re = re.compile(
        r"^\s*\d+\s+\d{1,2}/\d{1,2}/2026\s+\w+\s+\w+\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+(-?\d+)",
        re.MULTILINE,
    )
    # The auction table has columns: STT | Ngày | TCPH | Mã TP | Kì hạn | GTGT | GTĐT | GTTT | LSTT | Δđcb
    # Try a wider regex that captures kỳ hạn + GTGT + GTĐT + GTTT + LSTT + Δ
    auc_re2 = re.compile(
        r"\b(\d{1,2})\s+24/6/2026\s+\w+\s+\w+\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+(-?\d+)",
        re.MULTILINE,
    )
    # Fallback: parse by tenor mention near auction results
    for tenor in [3, 5, 10, 15, 30]:
        # Pattern: "...<tenor>  <gtgt>  <gtdt>  <gttt>  <lstt>  <delta>"
        pat = re.compile(
            rf"\b{tenor}\s+(\d[\d.,]*)\s+(\d[\d.,]*)\s+(\d[\d.,]*)\s+(\d[\d.,]*)\s+(-?\d+)",
            re.MULTILINE,
        )
        pm = pat.search(text)
        # Only take if in auction section — heuristic: find near "đấu thầu" keyword
        if pm:
            # Check context — search "đấu thầu" within 3000 chars before
            pos = pm.start()
            window = text[max(0, pos - 3000):pos]
            if "đấu thầu" in window.lower() or "kết quả đấu" in window.lower():
                r.auction[f"{tenor}Y"] = {
                    "gtgt": float(pm.group(1).replace(".", "").replace(",", ".")),
                    "gtdt": float(pm.group(2).replace(".", "").replace(",", ".")),
                    "gttt": float(pm.group(3).replace(".", "").replace(",", ".")),
                    "lstt": float(pm.group(4).replace(",", ".")),
                    "delta_bp": float(pm.group(5)),
                }

    # 4. Secondary (L291-294)
    r.secondary_total = _find_amount(text, "đạt 99,404", "99.404") or _regex_amount(text, r"thứ cấp đạt\s+([\d.]+)\s+tỷ")
    r.secondary_outright_avg_day = _regex_amount(text, r"outright trung bình ngày là\s+([\d.]+)\s+tỷ")
    r.secondary_outright_wow_pct = _regex_pct(text, r"outright.*?tăng\s+([\d.]+)%")
    r.secondary_repo_avg_day = _regex_amount(text, r"repo trung bình ngày là\s+([\d.]+)\s*tỷ")
    r.secondary_repo_wow_pct = _regex_pct(text, r"repo.*?tăng\s+([\d.]+)%")

    # 5. Foreign (L296-297) — "bán ròng khoảng 606 tỷ" or "171 tỷ" (varies W25 vs W26)
    r.foreign_net_sell_week = _regex_amount(text, r"bán ròng khoảng\s+([\d.,]+)\s*tỷ đồng trong tuần")
    r.foreign_net_sell_ytd = _regex_amount(text, r"tổng giá trị\s*bán\s*ròng.*?đạt khoảng\s+([\d.,]+)\s*tỷ đồng")

    # 6. FX pairs (L216-223) — "USD/VND  26,300  26,321  -0.08%  8.12%"
    for pair in ["USD/VND", "EUR/USD", "USD/CNY", "USD/JPY", "GBP/USD", "USD index"]:
        pat = re.compile(rf"{re.escape(pair)}.*?([\d,.]+)\s+([\d,.]+)\s+(-?[\d.]+%)\s+(-?[\d.]+%)", re.I)
        pm = pat.search(text)
        if pm:
            rate_str = pm.group(1).replace(",", "")
            try:
                rate = float(rate_str)
            except ValueError:
                rate = float(pm.group(1).replace(".", "").replace(",", "."))
            wow = float(pm.group(3).replace("%", "").replace(",", "."))
            ytd = float(pm.group(4).replace("%", "").replace(",", "."))
            r.fx_pairs[pair] = {"rate": rate, "wow_pct": wow, "ytd_pct": ytd}

    # 7. OMO (L99-102)
    r.omo_offered = _regex_amount(text, r"bơm ra\s+([\d.,]+)\s+tỷ đồng")
    r.omo_won = _regex_amount(text, r"bơm ra.*?([\d.,]+)\s+tỷ đồng.*?OMO") or _regex_amount(text, r"trúng thầu\s+([\d.,]+)\s+tỷ")
    r.omo_matured = _regex_amount(text, r"đáo hạn.*?([\d.,]+)\s*nghìn tỷ") or _regex_amount(text, r"đáo hạn.*?([\d.]+)\s+tỷ")
    r.omo_net = _regex_amount(text, r"bơm ròng.*?([\d.,]+)\s*nghìn tỷ")
    r.omo_outstanding = _regex_amount(text, r"lưu hành.*?([\d.,]+)\s*nghìn tỷ")
    m = re.search(r"OMO.*?([\d,]+)%", text, re.I)
    if m:
        r.omo_rate = float(m.group(1).replace(",", "."))

    # 8. TPDN (L353-378)
    m = re.search(r"phát hành\s+(\d+)\s+đợt", text, re.I)
    if m:
        r.tpdn_issues_month = int(m.group(1))
    r.tpdn_total_month = _regex_amount(text, r"phát hành.*?([\d.,]+)\s+tỷ đồng.*?tháng 6")
    r.tpdn_ytd = _regex_amount(text, r"từ đầu năm.*?([\d.,]+)\s+tỷ đồng")
    r.tpdn_buyback_ytd = _regex_amount(text, r"mua lại.*?([\d.,]+)\s*tỷ")
    r.tpdn_due_rest_year = _regex_amount(text, r"đáo hạn.*?([\d.,]+)\s*tỷ.*?còn lại")

    return r


def _regex_amount(text: str, pattern: str) -> Optional[float]:
    """Generic regex for VN-formatted amounts (dot thousands, comma decimal)."""
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    raw = m.group(1)
    # Normalize: "1.825.561" → 1825561, "4,5" → 4.5
    if "." in raw and "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "." in raw:
        # Could be VN thousands (1.825 = 1825) or decimal (3.52)
        parts = raw.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            raw = raw.replace(".", "")  # thousands
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _regex_pct(text: str, pattern: str) -> Optional[float]:
    """Generic regex for percentage."""
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace("%", "").replace(",", "."))
    except ValueError:
        return None


def _find_amount(text: str, *literals: str) -> Optional[float]:
    """Find amount near any literal string (e.g. '99.404' or '99,404')."""
    for lit in literals:
        idx = text.find(lit)
        if idx >= 0:
            cleaned = lit.replace(".", "").replace(",", "")
            try:
                return float(cleaned)
            except ValueError:
                pass
    return None


@dataclass
class ParsedVNBAFull:
    """VNBA full extraction — central banks + 10Y govy multi-country + commodities + equity + bank PBT."""
    # Central bank rates (L292-316)
    cb_rates: dict = field(default_factory=dict)  # {"FED": "3.50-3.75%", "ECB": "2.25%", ...}
    # 10Y govy yields multi-country (L319-343)
    govy_10y: dict = field(default_factory=dict)  # {"US": 4.37, "VN": 4.52, ...}
    # Commodities (L344-392)
    commodities: dict = field(default_factory=dict)  # {"gold": 4087.01, "brent": 71.99, ...}
    # Equity indices (L323-342)
    equities: dict = field(default_factory=dict)  # {"Dow": {"wow": 0.60, "ytd": 18.39}, ...}
    # FX pairs (L301-316)
    fx: dict = field(default_factory=dict)  # {"DXY": 101.357, "USDJPY": 161.731, ...}
    # Bank PBT Q2 (L657-679)
    bank_pbt: dict = field(default_factory=dict)  # {"VPB": {"pbt": 7499, "yoy": 51.9}, ...}
    # VN gold (L701-724)
    sjc_buy: Optional[float] = None
    sjc_sell: Optional[float] = None
    # CPI expectation
    cpi_mom_expected: Optional[float] = None
    cpi_avg_2026_expected: Optional[float] = None
    # LNH (L729-743)
    lnh_vnd: dict = field(default_factory=dict)  # {"ON": 3.00, "1W": 7.90, ...}
    lnh_usd: dict = field(default_factory=dict)
    # OMO (L744-760)
    omo_offered: Optional[float] = None
    omo_won: Optional[float] = None
    omo_rate: Optional[float] = None


def parse_vnba_full(text: str) -> ParsedVNBAFull:
    """Parse VNBA weekly for ALL must-have indicators (Phase 1)."""
    r = ParsedVNBAFull()

    # 1. Central bank rates — table row "FED  Mỹ  3.50%-3.75% 3.75%-4.00%" (single range) or "ECB  EURO Zone  2.25%  2.00%" (point)
    # FED has range format; others have point. Handle both.
    cb_patterns = [
        (r"FED\s+Mỹ\s+([\d.]+%-[\d.]+%)\s+([\d.]+%-[\d.]+%)", "FED"),
        (r"ECB\s+EURO Zone\s+([\d.]+%)\s+([\d.]+%)", "ECB"),
        (r"BOJ\s+([\d.]+%)\s+([\d.]+%)", "BOJ"),
        (r"PBoC\s+Tr/Quốc\s+([\d.]+%)\s+([\d.]+%)", "PBoC"),
        (r"RBA\s+Úc\s+([\d.]+%)\s+([\d.]+%)", "RBA"),
        (r"BoE\s+Anh\s+([\d.]+%)\s+([\d.]+%)", "BoE"),
        (r"BOK\s+Hàn quốc\s+([\d.]+%)\s+([\d.]+%)", "BOK"),
    ]
    for pat, name in cb_patterns:
        m = re.search(pat, text)
        if m:
            r.cb_rates[name] = {"current": m.group(1), "previous": m.group(2)}

    # 2. 10Y govy yields — table format: "<Country>  <yield>  -0.15%  -0.12%  0.20%  0.09%"
    # Countries in English. Yield on same line as country name.
    govy_countries = {
        "United States": "US", "United Kingdom": "UK", "Japan": "JP",
        "Australia": "AU", "Germany": "DE", "China": "CN",
        "Singapore": "SG", "Hàn Quốc": "KR", "Vietnam": "VN", "Indonesia": "ID",
    }
    for country_en, code in govy_countries.items():
        # Pattern: country name + yield (4 decimals) + WoW% + ...
        pat = re.compile(rf"{re.escape(country_en)}\s+(\d\.\d{{3,4}})\s+(-?[\d.]+%)", re.I)
        pm = pat.search(text)
        if pm:
            yield_val = float(pm.group(1))
            wow = float(pm.group(2).replace("%", "").replace(",", "."))
            r.govy_10y[code] = {"yield": yield_val, "wow_pct": wow}

    # 3. Commodities (key ones) — gold/brent/DXY
    # DXY (also in FX)
    m = re.search(r"DXY\s+(\d{2,3}\.\d{1,4})", text)
    if m:
        r.fx["DXY"] = float(m.group(1))
    # Gold — table "Vàng USD/t.oz  4087.01"
    m = re.search(r"Vàng USD/t\.oz\s+(\d{3,5}\.\d{1,2})", text, re.I)
    if m:
        r.commodities["gold"] = float(m.group(1))
    # Brent — narrative "giá dầu Brent giao tháng 8 giảm 4,34%, chốt phiên ở mức 71,99"
    # OR table "Dầu thô  69.230"
    m = re.search(r"Brent[^.]{0,60}mức\s+(\d{2,3}[.,]\d{1,2})", text, re.I)
    if m:
        r.commodities["brent"] = float(m.group(1).replace(",", "."))
    else:
        m = re.search(r"Dầu thô\s+(\d{2,3}\.\d{1,4})", text)
        if m:
            r.commodities["brent_wti"] = float(m.group(1))

    # 4. Equity indices — table format: "Dow Jones  +0.60%  +1.65%  +7.93%  +18.39%  +52.03%"
    eq_names = {
        "Dow Jones": "Dow", "S&P 500": "S&P500", "Nasdaq": "Nasdaq",
        "DAX": "DAX", "FTSE 100": "FTSE", "CAC 40": "CAC",
        "Nikkei 225": "Nikkei", "Shanghai": "Shanghai", "Hang Seng": "HangSeng",
    }
    for full_name, key in eq_names.items():
        pat = re.compile(rf"{re.escape(full_name)}\s+([+-]?[\d.]+%)\s+([+-]?[\d.]+%)\s+([+-]?[\d.]+%)", re.I)
        pm = pat.search(text)
        if pm:
            r.equities[key] = {
                "wow_pct": float(pm.group(1).replace("%", "").replace(",", ".")),
                "mom_pct": float(pm.group(2).replace("%", "").replace(",", ".")),
                "ytd_pct": float(pm.group(3).replace("%", "").replace(",", ".")),
            }

    # 5. Bank PBT (L657-679) — "VPB  ~ 7.499  + 51,9%" or "STB  ~ 1.666  - 42,4%"
    bank_re = re.compile(
        r"\b(VPB|HDB|VIB|OCB|TCB|VCB|BIDV|CTG|TPB|ACB|LPB|EIB|STB)\s+~\s*([\d.]+)\s*([+-])\s*([\d.,]+)%",
        re.I,
    )
    for m in bank_re.finditer(text):
        ticker = m.group(1).upper()
        try:
            pbt = float(m.group(2).replace(".", ""))
            sign = 1 if m.group(3) == "+" else -1
            yoy = sign * float(m.group(4).replace(",", "."))
            r.bank_pbt[ticker] = {"pbt_b_vnd": pbt, "yoy_pct": yoy}
        except ValueError:
            pass

    # 6. VN gold SJC
    m = re.search(r"SJC.*?(\d{3},?\d)\s*-\s*(\d{3},?\d)\s*trđ", text, re.I)
    if m:
        r.sjc_buy = float(m.group(1).replace(",", "."))
        r.sjc_sell = float(m.group(2).replace(",", "."))

    # 7. CPI expectations
    m = re.search(r"CPI.*?(\d[.,]\d+)\s*%.*?(?:tháng 6|kỳ vọng)", text, re.I)
    if m:
        r.cpi_mom_expected = float(m.group(1).replace(",", "."))
    m = re.search(r"(?:bình quân 2026|CPI bình quân.*?2026).*?(\d[.,]\d+)\s*%", text, re.I)
    if m:
        r.cpi_avg_2026_expected = float(m.group(1).replace(",", "."))

    # 8. LNH VND/USD (L729-743) — table 8 tenors
    for tenor in ["ON", "1W", "2W", "1M", "3M", "6M"]:
        pat = re.compile(rf"{tenor}\s+VND\s+(\d[.,]\d+)\s*%?", re.I)
        pm = pat.search(text)
        if pm:
            r.lnh_vnd[tenor] = float(pm.group(1).replace(",", "."))
        pat = re.compile(rf"{tenor}\s+USD\s+(\d[.,]\d+)\s*%?", re.I)
        pm = pat.search(text)
        if pm:
            r.lnh_usd[tenor] = float(pm.group(1).replace(",", "."))

    # 9. OMO
    r.omo_offered = _regex_amount(text, r"chào thầu\s+([\d.,]+)\s*tỷ")
    r.omo_won = _regex_amount(text, r"trúng thầu\s+([\d.,]+)\s*tỷ")
    m = re.search(r"OMO.*?([\d,]+)\s*%/năm", text, re.I)
    if m:
        r.omo_rate = float(m.group(1).replace(",", "."))

    return r
