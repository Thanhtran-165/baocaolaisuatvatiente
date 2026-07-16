# Data Cards — 35 chỉ số + 4-week schema + narrative rules

## 35 chỉ số theo 4 nhóm

### Tab 1 — Thị trường tiền tệ (9 card)
| # | Key | Name | Source primary | Chart? |
|---|---|---|---|---|
| 1 | `interbank_on` | LNH Overnight | SBV | ✅ |
| 2 | `interbank_1w` | LNH 1 tuần | SBV | ✅ |
| 3 | `interbank_1m` | LNH 1 tháng | SBV | ✅ |
| 4 | `omo_net` | OMO (cung/rút tuần) | SBV | ✅ |
| 5 | `policy_rates` | LS chính sách | SBV | — |
| 6 | `deposit_12m` | LS huy động 12T | VNBA | ✅ |
| 7 | `lending_12m` | LS cho vay 12T | VNBA | ✅ |
| 8 | `credit_yoy` | Tín dụng YoY | VNBA | — |
| 9 | `m2_yoy` | M2 YoY | VNBA | — |

### Tab 2 — Thị trường trái phiếu (10 card)
| # | Key | Name | Source primary | Chart? |
|---|---|---|---|---|
| 10 | `gov_2y_yield` | LSTP 2 năm | VBMA | ✅ |
| 11 | `gov_5y_yield` | LSTP 5 năm | VBMA | ✅ |
| 12 | `gov_10y_yield` | LSTP 10 năm | VBMA | ✅ |
| 13 | `yield_slope_10y_2y` | Slope 10Y−2Y | Tính | ✅ |
| 14 | `tpcp_bid_offer_ratio` | TPCP bid/offer | VBMA | ✅ |
| 15 | `tpcp_secondary_value` | TPCP secondary | VBMA | ✅ |
| 16 | `tpcp_foreign_holdings` | TPCP foreign holdings | VBMA | ✅ |
| 17 | `tpdn_issuance` | TPDN phát hành | VBMA | — |
| 18 | `tpcp_tenor_mix` | TPCP tenor mix | VBMA | — |
| 19 | `yield_change_10y_bp` | Yield change tuần (bp) | HNX FTP | ✅ |

### Tab 3 — Ngoại hối & toàn cầu (9 card)
| # | Key | Name | Source primary | Chart? |
|---|---|---|---|---|
| 20 | `fx_central` | Tỷ giá trung tâm | SBV | ✅ |
| 21 | `fx_tm_avg` | Tỷ giá TM | SBV | ✅ |
| 22 | `fx_band_pct` | Biến độ vs trung tâm | Tính | ✅ |
| 23 | `dxy` | DXY | VNBA/FRED | ✅ |
| 24 | `us_10y` | US 10Y yield | VNBA/FRED | ✅ |
| 25 | `us_2y` | US 2Y yield | VNBA/FRED | ✅ |
| 26 | `gold_usd_oz` | Gold spot | VNBA | ✅ |
| 27 | `brent_usd_bbl` | Brent crude | VNBA | ✅ |
| 28 | `central_bank_action` | Fed/ECB/BOJ action | VNBA | — |

### Tab 4 — CK & bối cảnh VN (7 card)
| # | Key | Name | Source primary | Chart? |
|---|---|---|---|---|
| 29 | `vnindex` | VN-Index | VNBA/vnstock | ✅ |
| 30 | `hose_liquidity` | Thanh khoản HOSE | VNBA | ✅ |
| 31 | `foreign_flow_eq` | Dòng ngoại CK | VNBA | ✅ |
| 32 | `cpi_yoy` | CPI YoY (monthly carryover) | VNBA | — |
| 33 | `iip_yoy` | IIP YoY (monthly carryover) | VNBA | — |
| 34 | `fdi_yoy` | FDI YoY (monthly carryover) | VNBA | — |
| 35 | `bank_pbt_quarterly` | Bank PBT quý (top 4 NHTM) | VNBA | — |

## Card types
- **Type A** (chart 12 tuần): có `has_chart: true`, `chart_source` upstream — PDF 4-week + upstream 12-week → line chart
- **Type B** (PDF-only 4-week): `has_chart: false`, `chart_source: null` — chỉ wow-strip sparkline từ PDF

## Schema — 4-week array

```json
{
  "gov_10y_yield": {
    "name_vi": "Lợi suất trái phiếu CP 10 năm",
    "definition": "Yield TPCP 10Y benchmark, đóng cửa thứ 6 tuần N",
    "values": [
      {"week": "2026-W23", "value": 3.70, "wow_pct": null},
      {"week": "2026-W24", "value": 3.75, "wow_pct": 1.35},
      {"week": "2026-W25", "value": 3.83, "wow_pct": 2.13},
      {"week": "2026-W26", "value": 3.85, "wow_pct": 0.52}
    ],
    "value_unit": "%",
    "trend_4w": "+4.1%",
    "streak": {"direction": "up", "weeks": 4},
    "comparisons": {"prev_month": 3.55},
    "source_primary": "VBMA",
    "source_check": "HNX yield curve",
    "signal": "RED",
    "narrative": "LSTP 10Y +15bp trong 4 tuần, kéo dài chuỗi tăng — NHNN vẫn bơm tiền dồi dào trong khi giá tiền dài hạn đã đắt lên.",
    "has_chart": true,
    "chart_source": "hnx_yield_curve"
  }
}
```

### Trường mới cho weekly
- `values[]` — mảng 4 điểm (thay `value` đơn)
- `trend_4w` — % biến động W-3 → W
- `streak` — `{"direction": "up"|"down", "weeks": N}`
- `wow_pct` — % thay đổi tuần trước
- `chart_source` — tên upstream (`hnx_yield_curve`, `fred_global`, `sbv_interbank`, `vnstock`, `null`)

## Signal semantics (rates-specific — NGƯỢC equity)
- `GREEN` = dovish/thuận (LNH↓, OMO bơm, LSTP↓)
- `RED` = hawkish/thắt chặt (LNH↑, OMO hút, LSTP↑)
- `AMBER` / `NEUTRAL` = không đổi

## Verdict badge mapping
- THUẬN (dovish) — green tint
- LƯỢNG (mild dovish) — cyan tint
- TRUNG TÍNH — amber tint
- THẮN CHẶT (hawkish) — red tint

## Narrative rules — "Người kể chuyện số liệu, KHÔNG phải người cho ý kiến"

| ❌ Tránh | ✅ Làm |
|---|---|
| "NHNN sẽ phải siết tiền tệ" | "LNH ON tăng 50bp tuần này, kéo dài chuỗi 3 tuần tăng — cùng lúc OMO chuyển từ bơm sang hút 5 nghìn tỷ" |
| "Tôi dự báo tuần sau khó khăn" | "LSTP 10Y +15bp trong 4 tuần, trong khi LNH ON vẫn giữ thấp — hai số này cùng kể câu chuyện giá tiền dài hạn đắt lên" |

**4 ĐỪNG**:
1. ĐỪNG dùng "tôi nghĩ/có thể/dự báo" → dùng "số liệu cho thấy", "cùng lúc"
2. ĐỪNG khuyên mua/bán/khuyến nghị → chỉ kể diễn biến số
3. ĐỪNG dùng tính từ cảm tính ("đáng lo", "tốt") → dùng số so sánh ("+50bp", "3 tuần liên tiếp")
4. ĐỪNG kết luận định hướng → mở câu hỏi cho người đọc

## Nguyên tắc KHÔNG placeholder
Chỉ đưa vào báo cáo những gì CÓ DỮ LIỆU THẬT. KHÔNG tạo card/section "THIẾU" cho phần chưa có data. Khi nguồn publish → chạy lại skill, card tự xuất hiện.


## DANH SÁCH CẤM — Speculation / Over-interpretation (BẮT BUỘC)

Tính trung thực là sống còn. Narrative KHÔNG được dùng các cụm từ speculation/over-interpretation sau (audit sẽ FAIL):

| Cụm từ cấm | Lý do | Thay thế bằng |
|---|---|---|
| "chốt lời" | Speculation về động cơ foreign — source chỉ báo số | "khi lợi suất đã tăng lên mức hấp dẫn hơn" |
| "bài học về kỷ luật" | Đánh giá chủ quan NHNN — SBV không tự đánh giá | "cách điều hành linh hoạt" |
| "rủi ro default chain" | Speculation nghiêm trọng về TPDN BĐS | "áp lực tái tài trợ" |
| "cạnh tranh gay gắt" | Subjective | (mô tả số liệu thay vì đánh giá) |
| "tín hiệu tích cực/đáng lo" | Subjective nhận định | (mô tả số liệu, để người đọc tự đánh giá) |
| "tôi nghĩ/có thể/dự báo" | Speculation cá nhân | "số liệu cho thấy", "cùng lúc" |
| "áp lực cuối quý" | Speculation nếu không có source | (chỉ khi source gốc nói cụ thể) |
| "chuẩn bị mùa tín dụng" | Speculation nếu không có source | (chỉ khi source gốc nói cụ thể) |

### Nguyên tắc cốt lõi
- Chỉ **trần thuật + kết nối insight** từ source gốc
- KHÔNG tự **đánh giá / đưa nhận định** về động cơ, lý do, ý đồ
- Khi nói về "why", phải dựa trên claim trực tiếp của source (SBV/VBMA/VNBA), không suy diễn
- Khi nói về "so what", mô tả hệ quả quan sát được, không dự báo

### Audit script
```bash
# Check speculation (must return 0)
grep -cE "chốt lời|bài học về kỷ luật|default chain|cạnh tranh gay gắt|tín hiệu tích cực|tôi nghĩ|có thể.*dự báo" report_polished.html
```


## VĂN PHONG: TỔNG HỢP VÀ BÁO CÁO (BẮT BUỘC)

### Nguyên tắc cốt lõi
Report đọc như **báo cáo tổng hợp số liệu + bối cảnh**, KHÔNG phải bài phân tích nhận định. Người đọc tự suy luận.

### Bảng CHO PHÉP / KHÔNG CHO PHÉP

| ✅ CHO PHÉP (tổng hợp báo cáo) | ❌ KHÔNG CHO PHÉP (nhận định dự báo) |
|---|---|
| "Số liệu cho thấy LNH ON giảm 255 đcb" | "NHNN sẽ phải thắt chặt" |
| "Theo VBMA, tỷ lệ trúng thầu 25%" | "Thị trường có thể phản ứng tiêu cực" |
| "Cùng lúc, Fed giữ nguyên 3,50-3,75%" | "Tôi dự báo Q3 khó khăn" |
| "Điều này phù hợp với số liệu trúng thầu thấp" | "Điều này có nghĩa NHNN đang muốn nới lỏng" |
| "Foreign bán ròng 171 tỷ, lũy kế 6.153 tỷ" | "Foreign đang chốt lời" |

### Audit ngoại suy quá mức (over-extrapolation)

**Khi nào giảm temperature LLM về 0.1-0.2**:
- Model đưa ra >3 cụm từ quan điểm cá nhân trong 1000 từ
- Model suy diễn nguyên nhân ("có thể do", "động lực chính là") mà source không nói
- Model gán ý đồ ("chiến lược", "chủ động dàn dựng") cho cơ quan phát hành
- Model dự báo tương lai ("sẽ", "có lẽ") vượt quá phạm vi báo cáo tuần

**Script kiểm tra tự động**:
```bash
# Đếm cụm ngoại suy trong report
python3 -c "
import re
text = open('report.html').read()
text = re.sub(r'<[^>]+>', ' ', text)
# Patterns cần check
for p in ['có thể do', 'chủ động', 'chiến lược', 'gợi ý', 'ý đồ', 
          'sẽ phải', 'có lẽ', 'điều này có nghĩa']:
    count = len(re.findall(p, text, re.I))
    if count > 0:
        print(f'  ⚠️ \"{p}\": {count} lần')
print('Check xong.')
"
```

**Verdict**:
- 0 cụm ngoại suy hoàn toàn mới → ✅ PASS
- 1-3 cụm → ⚠️ Cần sửa từng cái
- >3 cụm → ❌ Giảm temperature về 0.1-0.2 + rewrite
