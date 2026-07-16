---
name: vn-rates-weekly
description: Báo cáo tuần thị trường lãi suất & tiền tệ Việt Nam — 4-week rolling window từ 3 nguồn PDF (SBV+VBMA+VNBA) + upstream 12-week chart (HNX/FRED/vnstock)
---

# VN Rates Weekly

Báo cáo tuần toàn cảnh thị trường lãi suất & tiền tệ Việt Nam — **4-week rolling window** + **12-week headline chart**, với verdict + narrative phong phú. Cover scope rộng: LNH, LSTP, TPCP/TPDN, FX, gold/oil/DXY, US rates, VN-Index, bank PBT.

**Độc lập** với `vn-macro-monthly` (cadence song song weekly + monthly). **Portable**: KHÔNG gọi API local, gọi trực tiếp upstream (HNX/SBV/FRED/vnstock) + 3 PDF weekly chính thức.

## Tích lũy cache — Rolling Window (BẮT BUỘC)

**Nguyên tắc**: Không fetch lại data đã có. Mỗi tuần chỉ fetch **1 tuần mới** (tuần N), giữ **3-4 tuần cũ** từ lần chạy trước.

### Cấu trúc cache
```
{project}/vn-rates-weekly/
├── cache/                          ← PERSISTENT — không xóa giữa các lần chạy
│   ├── sbv_2026-W23.txt            ← giữ từ lần trước
│   ├── sbv_2026-W24.txt
│   ├── sbv_2026-W25.txt
│   ├── sbv_2026-W26.txt            ← mới fetch lần này
│   ├── sbv_2026-W27.txt            ← TUẦN N (mới)
│   ├── vbma_W23.txt ... W27.txt
│   ├── vnba_W23.txt ... W27.txt
│   └── chart_data.json             ← upstream HNX/FRED (re-fetch mỗi lần)
├── 2026/
│   └── W27/
│       ├── report.html             ← output
│       └── report.json
```

### Fetch strategy (rolling)
```
Lần 1 (W26): fetch 4 tuần [W23, W24, W25, W26]  ← full fetch
Lần 2 (W27): 
  1. Check cache: W23-W26 đã có?
  2. Chỉ fetch W27 (mới)                           ← 3 files mới, không re-fetch cũ
  3. Tổng cache: W23-W27 (5 tuần)
  4. Xóa W22 trở về trước (nếu có)                  ← rolling cleanup
  5. Pipeline dùng 4 tuần [W24, W25, W26, W27]     ← window trượt
```

### Cleanup rule
- Giữ **5 tuần** trong cache (4 tuần dùng + 1 buffer)
- Tuần cũ hơn 5 → **tự động xóa** khi chạy pipeline
- Chart data (HNX/FRED): re-fetch mỗi lần (12 tuần history, không cache)

### Lợi ích
| Trước (full fetch mỗi lần) | Sau (rolling cache) |
|---|---|
| 12 PDFs × mỗi lần chạy | **3-4 PDFs** (chỉ tuần mới) |
| ~2 phút fetch | **~30 giây** fetch |
| Risk: SBV/VBMA rate limit | **Ít request hơn** |
| VNBA 4 tuần mỗi lần | **VNBA 1 tuần** mỗi lần |

### Script
```bash
# Pipeline tự động check cache → chỉ fetch thiếu
python3 scripts/run_pipeline.py --week 2026-W27 --out ./output/
# → Pipeline sẽ:
#   1. Check cache/ có W24-W26 không?
#   2. Nếu có → chỉ fetch W27 (SBV+VBMA+VNBA)
#   3. Nếu không → full fetch 4 tuần (fallback)
#   4. Cleanup tuần cũ (>5)
```


## `--quick` flag (v2.3 fix premortem — target audience-aware)

**Mặc định**: full pipeline (narrative 2-phase, 7.000 từ, 6 sections).
**`--quick`**: dashboard numbers + verdict 1 câu, skip narrative 2-phase.

```bash
/vn-rates-weekly 2026-W27 --quick
# → Chỉ fetch + extract + render dashboard (numbers + charts + verdict)
# → Skip: narrative 2-phase, prose extraction, 7.000 từ
# → Output: ~2.000 từ, dashboard numbers, 1-2 câu verdict
# → Thời gian: ~10 phút (vs 30 phút full)
```

**Khi nào dùng `--quick`**:
- Trader/investor cần update nhanh
- AI feed (downstream consumption — cần JSON, không cần prose)
- First pass trước khi chạy full

**Khi nào dùng full (mặc định)**:
- Analyst cần depth
- Publish công khai
- Weekly report chính thức

## Workflow 4 bước

### Bước 1: Pre-flight all-or-nothing (BẮT BUỘC)

Kiểm tra 12 PDFs (3 nguồn × 4 tuần) tồn tại + upstream deps. Nếu thiếu → **DỪNG**, không tạo thư mục (máy sạch).

```
User: /vn-rates-weekly 2026-W26
  ↓
1. Detect tuần N (thứ 2 gần nhất đã kết thúc)
2. Enumerate 4 tuần [N-3, N-2, N-1, N]
3. Tet/holiday skip → auto-backfill N-(x+1), flag tet_skip
4. HEAD check 12 PDFs + FRED_API_KEY + vnstock
5. **FRED key validity test** (v2.3 — xem FRED API Key Validity Check bên dưới)
#### FRED API Key Validity Check (BẮT BUỘC — v2.3 fix premortem)

Preflight hiện tại chỉ check `FRED_API_KEY` tồn tại. **Thêm**: test 1 request xem key valid:

```bash
python3 -c "
import os, sys, urllib.request, json
key = os.environ.get('FRED_API_KEY', '')
if not key:
    print('❌ FRED_API_KEY not set'); sys.exit(1)
# Test request — DGS10 latest
url = f'https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={key}&file_type=json&limit=1&sort_order=desc'
try:
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    if 'observations' in data:
        print(f'✅ FRED key valid — DGS10 latest: {data["observations"][0]["value"]}')
    else:
        print(f'❌ FRED key invalid or error: {data}'); sys.exit(1)
except Exception as e:
    print(f'❌ FRED request failed: {e}'); sys.exit(1)
"
```

**Nếu key invalid/expired**: DỪNG pipeline, flag user "FRED_API_KEY cần renewal".

  ↓
12/12 + deps OK? → Bước 2  |  thiếu? → DỪNG + đề xuất tuần thay thế
```

→ Xem `references/preflight_check.md` cho Tet calendar + retry hints + partial override workflow.
#### Tet/holiday coverage check (v2.3 fix premortem)

Verify `references/preflight_check.md` cover **TẤT CẢ ngày lễ VN**:

| Lễ | Loại | Ngày |
|---|---|---|
| Tết Dương lịch | Cố định | 1/1 |
| Tết Nguyên Đán (âm lịch) | Di động | ~Jan-Feb |
| Giỗ tổ Hùng Vương | Âm lịch | 10/3 âm |
| Giải phóng miền Nam | Cố định | 30/4 |
| Quốc tế Lao động | Cố định | 1/5 |
| Quốc khánh | Cố định | 2/9 |
| Quốc tang (if applicable) | Ad hoc | Variable |

**Nếu thiếu ngày lễ**: tuần đó fetch sẽ FAIL mà không flag đúng lý do.


### Bước 2: Fetch 12 PDFs + upstream headline

```bash
# 12 PDFs (3 nguồn × 4 tuần)
python3 scripts/fetch_sources.py --week 2026-W26 --out ./sources_cache

# SBV: curl article → regex <embed src> → curl PDF → pdftotext
# VBMA: curl listing → regex 4 hrefs → curl PDF (%20 encode) → pdftotext
# VNBA: curl hashtag → regex article → regex CDN PDF → curl PDF → pdftotext

# Upstream (12 tuần cho ~12 card Type A)
python3 scripts/fetch_sources.py --week 2026-W26 --out ./sources_cache --upstream-only
# HNX yield curve/auction, FRED (DGS10/DGS2/DTWEXBGS), vnstock VNINDEX
#### vnstock upstream error handling (v2.3 fix premortem)

```python
# Trong fetch_sources.py — upstream fetch
try:
    from vnstock import Quote
    q = Quote(symbol='VNINDEX', source='VCI')
    df = q.history(start=..., end=..., interval='1D')
    if df is None or df.empty:
        raise ValueError("VNINDEX empty response")
except Exception as e:
    print(f"⚠️ VNINDEX fetch failed: {e}")
    print("   → Flag 'VNINDEX data missing', chart sẽ có gap")
    vnindex_data = None  # downstream handle None
```

**Nếu VNINDEX fail**: flag rõ trong report "VNINDEX data missing this week" thay vì silent gap.

```

→ Xem `references/sources_overview.md` cho URL patterns + pitfalls từng nguồn.

#### ⚠️ PDF Week Verification (BẮT BUỘC sau fetch — v2.3 fix premortem)

Sau khi fetch 12 PDFs, verify mỗi PDF **thuộc đúng tuần** yêu cầu:

```bash
python3 -c "
import re, sys, glob
# Expected week from --week param
expected_week = sys.argv[1]  # e.g. '2026-W27'
# Parse week number
year, week_num = expected_week.split('-W')
# PDF filenames contain week — check
for f in sorted(glob.glob('sources_cache/*.txt')):
    basename = os.path.basename(f)
    if expected_week not in basename and f'W{week_num}' not in basename:
        # Also check content for date range
        content = open(f).read()[:500]
        print(f'⚠️ {basename}: filename không match week {expected_week}')
        # Flag but don't fail — content may still be correct
print('PDF week verification done.')
" 2026-W27
```

**Nếu PDF sai tuần** (vd fetch nhầm tuần trước): DỪNG, re-fetch. KHÔNG extract từ PDF sai tuần.


### Bước 3: Extract 35 chỉ số + 4 rules + narrative

Parse PDF text → `values[]` 4-week array. Áp 4 rules:

| Rule | Nội dung |
|---|---|
| **1. Time consistency** | `data_cutoff` = thứ 6 tuần N. PDF lấy tuần ≤ cutoff |
| **2. Frequency** | Chỉ weekly (WoW). Monthly cards (CPI/IIP/FDI) flag `monthly_carryover` |
| **3. Conflict resolution** | Priority: SBV > VBMA > VNBA (MON: enhanced v2.3 — nếu lệch >5%, flag both, KHÔNG auto-pick)
#### Conflict resolution enhanced (v2.3 fix premortem)

Khi lệch >5% giữa 2 nguồn, **KHÔNG auto-pick priority**. Thay vào đó:

1. Flag "CẢ HAI nguồn đều có thể đúng — lệch >5%"
2. Verify với HNX benchmark (nếu có — cho LSTP)
3. Report cả 2 giá trị + flag "data discrepancy"
4. Chỉ pick priority nếu benchmark confirm

**Lý do**: priority = source authority, KHÔNG phải accuracy. SBV có thể intentionally understated.
 (monetary); VNBA > VBMA (broad); HNX > VBMA (LSTP). Sai số <2% OK, 2-5% flag, >5% dùng priority |
| **4. Unit convention** | 8 suffix + `_wow_pct`, `_4w_trend_pct` |

Cross-check 3 nguồn → resolve conflicts → populate `values[]`:

```python
from extract_cards import parse_vbma_yields, parse_sbv_interbank, resolve_cross_source

# Mỗi nguồn parse riêng
vbma = parse_vbma_yields(vbma_text)  # 2Y/5Y/10Y yields
sbv = parse_sbv_interbank(sbv_text)  # LNH ON/1W/1M, FX, OMO

# Cross-check
resolved = resolve_cross_source(sbv.overnight, vbma_interbank_on)
```

### Bước 3.1: NARRATIVE GENERATION (BẮT BUỘC — quyết định chất lượng sản phẩm)

**Narrative là phần quan trọng nhất của báo cáo — không phải data extraction.**
Pipeline auto chỉ tạo data foundation. Report cuối phải có narrative depth
tương đương bản W26 manual (7.000+ từ, 6 sections).

#### Quy trình 2-phase (BẮT BUỘC để đạt depth)

**Phase 1: Đọc sâu từng tuần (4 cluster)**
- Đọc 3 file PDF text (SBV+VBMA+VNBA) của MỖI tuần riêng biệt
- Viết narrative tuần đó (~1.500-2.000 từ/tuần)
- Focus: diễn biến tuần đó + WHY + SO WHAT

**Phase 2: Cross-week synthesis (~7.000 từ tổng)**
- Merge 4 cluster narratives thành 6 sections theo chủ đề
- KHÔNG copy-paste — viết lại liền mạch theo timeline
- Thêm cross-week analysis: "đầu tháng → giữa tháng → cuối tháng"

#### Format requirements (BẮT BUỘC)

Mỗi prose-card phải có:

1. **`<h4 class="subsection">`** cho mỗi đoạn (KHÔNG wall of text)
   - VD: `<h4 class="subsection">Đầu tháng — thanh khoản căng</h4>`
   - VD: `<h4 class="subsection">Giữa tháng — đáy thanh khoản</h4>`
   - Minimum 4-5 h4 per section

2. **`<strong>` cho số liệu trọng yếu** (ratio ≥ 0.5 strong/p)
   - VD: `LNH ON đạt <strong>4,26%</strong>, giảm <strong>255 đcb</strong>`
   - Mỗi số quan trọng phải bold

3. **`<blockquote>` cho insight quan trọng** (1-2 per section)
   - VD: `<blockquote>LNH ON giảm 255 đcb trong tháng — đợt giảm mạnh nhất.</blockquote>`

4. **`<ul><li>` cho liệt kê** (khi có 3+ yếu tố)
   - VD: động lực, rủi ro, catalysts

5. **Minimum word count**: 7.000 từ tổng (test W26 đạt 6.100 → chưa đủ)

### Bước 3.2: CHART HINTS (BẮT BUỘC — sau mỗi chart)

Sau khi inject charts (Bước 6), BẮT BUỘC thêm hint cho mỗi chart:

**Quy tắc hint** (xem `references/rendering.md` Chart Hints section):
- Hint nằm **SAU** chart (không trước)
- 3 lớp nội dung: ý nghĩa kinh tế + giá trị hiện tại ngầm chỉ + bất thường
- Hint phải lấy số từ chart data thực (KHÔNG chung chung)

**Danh sách hints bắt buộc**:
| Chart | Hint phải nói |
|---|---|
| LNH VND | ON dao động rộng → nhạy OMO; spread 1W-ON bất thường |
| Yield curve | Dốc lên normal; curve dịch lên → chi phí vay tăng |
| Spread | Steepening/flattening; đoạn nào tăng nhiều nhất |
| Slope | Dương = không suy thoái; so quốc tế |
| Convexity | Âm/dương → demand đoạn giữa |
| US 10Y | Fed hawkish/dovish; trend 12 tuần |

### BƯỚC 4 BẮT BUỘC: RENDER POLISHED (KHÔNG render_report_v2)

**Pipeline phải dùng `render_polished.py` + inject charts, KHÔNG dùng `render_report_v2.py`.**

`render_report_v2.py` tạo bản đơn giản (1.300 từ, 3 charts) — **KHÔNG đạt tiêu chuẩn**.
`render_polished.py` đọc `narrative_final.md` (từ Bước 3.1) + inject 9 charts + hints → bản đầy đủ.

**Quy trình render (BẮT BUỘC theo đúng thứ tự)**:

1. `render_polished.py --narrative narrative_final.md --out report.html`
2. Inject LNH toggle (7 kỳ hạn VND, data từ SBV cache)
3. Inject HNX yield curve 12 tuần (data từ `chart_hnx_yields.json` hoặc fetch fresh)
4. Inject yield curve snapshot (8 tenors, đầu kỳ vs cuối kỳ)
5. Inject spread bar chart (8 tenors, bp)
6. Inject slope chart 12 tuần (10Y−2Y)
7. Inject convexity chart 12 tuần (2×5Y−2Y−10Y)
8. Inject FRED US 10Y + DXY (12 tuần, data từ `chart_fred.json`)
9. Inject chart hints (7 hints, sau mỗi chart — Bước 3.2)
10. Fix JS: `const chart = new Chart(...)`, `lnhChart = chart`, toggle handler, `spanGaps: true`, `borderDash`

**Tiêu chuẩn output (BẮT BUỘC — phải đạt ≥80% so với W26 chuẩn)**:

| Metric | Minimum | W26 chuẩn |
|---|---|---|
| **Charts** | 9 | 9 |
| **h4 subsections** | 30+ | 36 |
| **strong bold** | 300+ | 450 |
| **blockquote** | 7+ | 11 |
| **Chart hints "Ý nghĩa"** | 4+ | 4 |
| **Toggle buttons** | 7 | 7 |
| **Audit gates** | 4/4 PASS | 4/4 |
| **Word count** | 6.000+ | 9.325 |

Nếu output không đạt minimum → **KHÔNG publish**, quay lại Bước 3.1.
| DXY | USD mạnh/yếu; áp lực tỷ giá VN |

**Narrative** — đóng vai "người kể chuyện số liệu, KHÔNG người cho ý kiến":
- ĐỪNG "tôi nghĩ/có thể/dự báo" → dùng "số liệu cho thấy"
- ĐỪNG khuyên mua/bán → chỉ kể diễn biến số
- ĐỪNG tính từ cảm tính → dùng số so sánh ("+50bp", "3 tuần liên tiếp")

→ Xem `references/data_cards.md` cho 35 chỉ số mapping + 4-week schema + narrative rules.

### Bước 3.5: DATA VERIFICATION (BẮT BUỘC — sống còn)

**Tính chính xác là sống còn với báo cáo tài chính.** Sau khi extract, BẮT BUỘC chạy `verify_data.py` — script re-parse độc lập các file `.txt` nguồn và đối chiếu từng số trong `report.json`:

```bash
python3 scripts/verify_data.py \
  --report report.json \
  --cache sources_cache/ \
  [--strict]  # threshold 0.1% thay vì 0.5%
```

**FAIL criteria (exit 1 → DỪNG, không render)**:
- Bất kỳ số nào lệch > 0.5% so với source gốc
- Source file thiếu (number trong report nhưng không trace được)
- Cross-check SBV LNH vs VBMA TB 5 ngày lệch > 5bp

**Verdict**:
- `✅ VERIFICATION PASSED` → tiếp tục Bước 4
- `❌ VERIFICATION FAILED` → inspect failures, fix parser, re-extract, re-verify. **KHÔNG BAO GIỜ render khi verify fail.**

Script re-parse độc lập với `build_report.py` (không import parsers chung) — đây là cross-check thực sự, bắt được bug parser mà cùng codebase không phát hiện.

### Bước 3.7: AUDIT TÍNH TRUNG THỰC (BẮT BUỘC — sống còn)

**Tính trung thực là yếu tố sống còn với báo cáo tài chính.** Sau khi verify số liệu (Bước 3.5), BẮT BUỘC chạy audit 3 chiều:

#### Audit 1: Số liệu chính xác (data accuracy)
- Extract 55+ số liệu trọng yếu từ report
- Đối chiếu từng số với PDF gốc (VN-format aware: comma decimal, dot thousands)
- Tolerange: ±0.01% cho percent, ±50 cho số tiền
- **FAIL** nếu bất kỳ số nào lệch hoặc bịa đặt

#### Audit 2: Coverage thông tin trọng yếu (information coverage)
- List ~43 thông tin trọng yếu từ 3 PDF (số liệu + insight)
- Kiểm tra từng cái có trong report không
- **Target: ≥80% coverage** (ưu tiên cao ≥95%)
- Bổ sung ngay các thông tin ưu tiên cao bị thiếu trước publish

#### Audit 3: Bóp méo / speculation (distortion check)
- Kiểm tra các cụm từ speculation/over-interpretation
- **DANH SÁCH CẤM TUYỆT ĐỐI** (KHÔNG được dùng trong narrative — xuất hiện trong output = FAIL):
  - "chốt lời" (speculation về động cơ foreign — source chỉ báo số)
  - "bài học về kỷ luật" (đánh giá chủ quan NHNN)
  - "rủi ro default chain" (speculation nghiêm trọng)
  - "cạnh tranh gay gắt" (subjective)
  - "tín hiệu tích cực/đáng lo" (subjective nhận định)
  - "tôi nghĩ/có thể/dự báo" → dùng "số liệu cho thấy", "cùng lúc"
  - "áp lực cuối quý" (speculation nếu không có source)
  - "chuẩn bị mùa tín dụng" (speculation nếu không có source)
  - "chủ động dàn dựng" (gán ý thức cho NHNN)
  - "dàn dựng" (mọi dạng — gán ý đồ điều hành có chủ đích)
  - "chủ động rút bớt" (gán ý thức — chỉ nói "rút bớt")
  - "chủ động tái cấu trúc" (gán ý thức — chỉ nói "tái cấu trúc")
  - "chiến lược kéo dài đáo hạn" (suy diễn ý đồ Chính phủ)
  - "gợi ý" (ngoại suy — chỉ dùng nếu source gốc nói)
  - "điều này có nghĩa" (LLM diễn giải vượt source)
  - "sẽ phải" (dự báo bắt buộc)
  - "chắc chắn rằng" (LLM thay thế thị trường đưa kết luận)
- **Nguyên tắc**: chỉ trần thuật + kết nối insight từ source, KHÔNG tự đánh giá/đưa nhận định

#### Audit 3 chạy SAU format (post-production) — BẮT BUỘC

**Thứ tự pipeline ĐÚNG** (lessons learned):
1. Viết narrative (LLM)
2. Audit ngoại suy (Bước 3.7)
3. Fix ngoại suy
4. **Re-audit ngoại suy** — phải PASS (0 issues)
5. Format post-production (bold/heading/blockquote)
6. **Re-audit ngoại suy SAU format** — phải PASS (0 issues)
7. Render HTML
8. **Re-audit ngoại suy SAU render** — phải PASS (0 issues)

**Lý do**: Format agent có thể (a) đọc narrative cũ chưa fix, (b) reintroduce từ cấm khi "tóm tắt" vào blockquote, (c) thêm diễn giải khi tạo heading. Mỗi bước xử lý text = rủi ro reintroduce.

**Script kiểm tra nhanh (chạy sau mỗi bước)**:
```bash
python3 -c "
import re
text = open('output_file').read()
CẨM = ['dàn dựng', 'chốt lời', 'bài học về kỷ luật', 'default chain', 
        'cạnh tranh gay gắt', 'chủ động rút', 'chủ động tái cấu trúc',
        'chiến lược kéo dài', 'gợi ý', 'điều này có nghĩa', 'sẽ phải',
        'chắc chắn rằng', 'ý đồ']
issues = [(p, text.lower().count(p)) for p in CẨM if p in text.lower()]
if issues:
    print('❌ CẨM WORDS FOUND:')
    for p, c in issues: print(f'  {p}: {c} lần')
    exit(1)
print('✅ 0 cấm words')
"
```


#### Pattern-based speculation detection (v2.3 fix premortem)

Ngoài exact match forbidden words, thêm **regex patterns** bắt speculation mới:

```bash
python3 -c "
import re
text = open('report.html').read()
text_plain = re.sub(r'<[^>]+>', ' ', text).lower()

# Exact match (existing)
EXACT_FORBIDDEN = ['chốt lời', 'dàn dựng', 'default chain', 'cạnh tranh gay gắt',
    'chủ động rút', 'chủ động tái cấu trúc', 'chiến lược kéo dài',
    'chắc chắn rằng', 'ý đồ']

# Pattern match (NEW v2.3 — bắt speculation không trong list)
PATTERN_FORBIDDEN = [
    r'có thể\s+do',           # 'có thể do quỹ hưu trí'
    r'điều này\s+(có nghĩa|cho thấy|ngầm chỉ)',  # LLM diễn giải
    r'dường như',              # suy diễn
    r'có vẻ',                  # suy diễn
    r'tôi nghĩ',               # nhận định cá nhân
    r'sẽ phải',                # dự báo bắt buộc
    r'chắc chắn',              # overconfidence
    r'(tín hiệu|dấu hiệu)\s+(tích cực|tiêu cực|đáng lo)',  # subjective
    r'NHNN\s+(đang muốn|có vẻ|dường như)',  # gán ý đồ NHNN
]

issues = []
for word in EXACT_FORBIDDEN:
    count = text_plain.count(word)
    if count > 0: issues.append(f'EXACT: "{word}" ({count} lần)')

for pattern in PATTERN_FORBIDDEN:
    matches = re.findall(pattern, text_plain)
    if matches: issues.append(f'PATTERN: /{pattern}/ ({len(matches)} lần)')

if issues:
    print('❌ SPECULATION DETECTED:')
    for i in issues: print(f'  {i}')
    exit(1)
print('✅ 0 speculation (exact + pattern)')
"
```

#### Audit 3.1: Ngoại suy quá mức (over-extrapolation check) — BẮT BUỘC

**Mô tả**: Kiểm tra khả năng LLM đưa ra quan điểm cá nhân, suy diễn nguyên nhân, hoặc dự báo tương lai vượt quá văn bản gốc.

**Phương pháp**:
1. Extract mọi cụm từ "diễn giải" trong report: "phản ánh", "cho thấy", "có thể do", "tín hiệu", "điều này có nghĩa"
2. Đối chiếu: cụm từ này có trong source gốc (SBV/VBMA/VNBA) không?
3. Nếu LLM thêm diễn giải mà source không có → **NGOẠI SUY** → phải sửa

**Script kiểm tra**:
```bash
python3 -c "
import re
report = open('report.html').read()
report_text = re.sub(r'<[^>]+>', ' ', report)
# Load source
source = ''
import glob
for f in glob.glob('sources_cache/*.txt'): source += open(f).read()

patterns = ['chủ động dàn dựng', 'chiến lược kéo dài', 'gợi ý', 'có thể do',
            'ý đồ', 'điều này có nghĩa', 'áp lực cuối quý', 'chuẩn bị mùa tín dụng']
for p in patterns:
    in_report = report_text.lower().count(p)
    in_source = source.lower().count(p)
    if in_report > 0 and in_source == 0:
        print(f'❌ NGOẠI SUY: \"{p}\" xuất hiện {in_report} lần trong report, 0 trong source')
    elif in_report > in_source * 2:
        print(f'⚠️ LLM THÊM: \"{p}\" report={in_report}, source={in_source}')
print('Done.')
"
```

**Tiêu chí PASS**: 0 ngoại suy hoàn toàn mới (source không có từ đó)

**Nếu phát hiện ngoại suy**:
1. Thay cụm ngoại suy bằng trần thuật trung tính
   - "chủ động dàn dựng" → "điều hành"
   - "chiến lược kéo dài đáo hạn" → "việc kéo dài đáo hạn"
   - "có thể do quỹ hưu trí" → "theo số liệu đặt thầu"
   - "gợi ý cầu tập trung" → "phù hợp với số liệu trúng thầu"
2. **Giảm temperature LLM** về 0.1-0.2 nếu có dấu hiệu model đưa quá nhiều quan điểm
3. Re-audit cho đến khi PASS

#### Văn phong: Tổng hợp và báo cáo (KHÔNG nhận định / dự báo)

**CHO PHÉP** (văn phong tổng hợp báo cáo):
- "Số liệu cho thấy..." ✅
- "Theo VBMA, LNH ON giảm 150 đcb" ✅
- "Cùng lúc, Fed giữ nguyên lãi suất" ✅
- "Điều này phù hợp với..." (nếu có data cross-check) ✅

**KHÔNG CHO PHÉP** (nhận định / dự báo):
- "NHNN sẽ phải thắt chặt" ❌
- "Thị trường có thể phản ứng..." ❌
- "Tôi dự báo Q3 khó khăn" ❌
- "Điều này có nghĩa NHNN đang muốn..." ❌ (gán ý đồ)
- "Động lực chính là..." ❌ (suy diễn nguyên nhân nếu source không nói)

**Rule**: Report phải đọc như **báo cáo tổng hợp số liệu + bối cảnh**, KHÔNG phải như **bài phân tích nhận định**. Người đọc tự suy luận.

#### Output audit
```bash
# Audit tự động (script)
python3 scripts/verify_data.py --report report.json --cache sources_cache/

# Audit narrative (manual review checklist)
# 1. grep "chốt lời\|bài học\|default chain\|cạnh tranh gay gắt" → phải = 0
# 2. Re-check 8 thông tin ưu tiên cao
# 3. Coverage ≥80%
```

**Verdict audit**:
- `✅ AUDIT PASSED` (≥80% coverage, 0 speculation, 55/55 số verified) → publish
- `⚠️ AUDIT NEEDS FIX` → fix issues, re-audit
- `❌ AUDIT FAILED` → **KHÔNG publish**, quay lại Bước 3

### Bước 4: Render HTML + QA quadruple-gate

```bash
# Render
python3 scripts/render_report.py \
  --report report.json \
  --template assets/weekly_template.html \
  --out report.html

# QA quadruple-gate (BẮT BUỘC — cả 4 phải PASS)
# Gate 1: JS syntax
python3 -c "import re; html=open('report.html').read(); s=re.findall(r'<script>(.*?)</script>',html,re.DOTALL); open('/tmp/r.js','w').write(s[-1])"
node --check /tmp/r.js && echo "✅ JS OK"

# Gate 2: Data verification (lặp lại từ Bước 3.5)
python3 scripts/verify_data.py --report report.json --cache sources_cache/

# Gate 3: Visual QA (Playwright)
NODE_PATH=/tmp/qa-weekly-runner/node_modules node scripts/qa_weekly.js \
  --url=file://$(pwd)/report.html --output=./qa-shots
```

**Quadruple-gate**:
1. **JS syntax** — `node --check`
2. **HTML structure** — div/section open/close balance (BẮT BUỘC — thiếu `</section>` vỡ layout toàn bộ)
3. **Data verification** — `verify_data.py` (sống còn)
4. **Visual QA** — Playwright (hero, tabs, charts, cards, console errors, section visibility, content position)
5. **Audit trung thực** — Bước 3.7 (coverage ≥80%, 0 speculation, 55/55 số verified)

### Gate 2: HTML Structure Check (BẮT BUỘC — lessons learned)

```bash
# Thiếu </section> hoặc </div> → layout vỡ toàn bộ, mọi section 0×0
python3 -c "
import re, sys
html = open('report.html').read()
errors = []
div_diff = html.count('<div') - html.count('</div>')
sec_diff = html.count('<section') - html.count('</section>')
if div_diff != 0: errors.append(f'div diff={div_diff} (thiếu {abs(div_diff)} </div>)')
if sec_diff != 0: errors.append(f'section diff={sec_diff} (thiếu {abs(sec_diff)} </section>)')
if errors:
    print('❌ HTML STRUCTURE BROKEN:', '; '.join(errors))
    sys.exit(1)
print('✅ HTML structure OK')
"
```


#### Word Count Gate (v2.3 fix premortem — BẮT BUỘC)

```bash
# Sau render, trước publish
python3 -c "
import re
html = open('report.html').read()
text = re.sub(r'<[^>]+>', ' ', html)
words = len(text.split())
if words < 6500:
    print(f'❌ FAIL: chỉ {words} từ (minimum 6.500, target 7.000)')
    exit(1)
print(f'✅ Word count: {words} (≥6.500)')
"
```

**Nếu < 6.500 từ**: DỪNG, quay lại Bước 3.1 expand narrative.

### Gate 4: Visual QA bổ sung (lessons learned)

Playwright QA ngoài checks hiện tại, THÊM:
- **Section visibility**: mỗi section active phải có `getBoundingClientRect().width > 0`
- **Content position**: verify chart nằm đúng section (`section.contains(canvas)`)
- **Tab switching**: click từng tab → verify content visible

### Render Architecture Rule (lessons learned)
- **KHÔNG post-process HTML** sau render script (sed/inject trực tiếp vào file output)
- Tất cả charts/data/hints phải được inject **trong render script**
- Nếu cần thay đổi → sửa render script + re-render hoàn chỉnh
- Lý do: post-process dễ xóa nhầm `</section>`, ghi đè thay đổi trước đó, inject sai vị trí

Expected: tất cả PASS. Kết quả: `✅ PASS` → done | `❌ FAIL` → fix rerun, **KHÔNG publish report fail**.

→ Xem `references/rendering.md` cho 15 patterns + 3 rates components + placement rule.

## Output

```
{project}/vn-rates-weekly/
├── history.json                    # append mỗi tuần, 6+ tuần → chart dài
├── 2026/
│   ├── W23/
│   │   ├── report.json             # data structured (nguồn dữ liệu chuẩn)
│   │   ├── report.html             # dashboard cuối
│   │   └── sources_cache/
│   │       ├── sbv_W23.pdf, sbv_W23.txt
│   │       ├── vbma_W23.pdf, vbma_W23.txt
│   │       └── vnba_W23.pdf, vnba_W23.txt
│   ├── W24/ ... W25/ ... W26/
```

## Verdict + Stance semantics (rates-specific — NGƯỢC equity)

| Signal | Meaning | Color |
|---|---|---|
| GREEN | dovish/thuận (LNH↓, OMO bơm, LSTP↓) | `--green:#10d98a` |
| RED | hawkish/thắt chặt (LNH↑, OMO hút, LSTP↑) | `--red:#ff4d6d` |
| AMBER/NEUTRAL | không đổi | `--amber:#fbbf24` |

| Verdict | Stance | Tint |
|---|---|---|
| THUẬN | dovish mạnh | green |
| LƯỢNG | mild dovish | cyan |
| TRUNG TÍNH | cân bằng | amber |
| THẮN CHẶT | hawkish | red |

## Phối hợp hệ sinh thái skill VN

```
vn-financial-data-collector  (DN cấp — equity data)
vn-macro-monthly            (VĨ MÔ monthly — CPI/PMI/IIP/FDI)
⭐ vn-rates-weekly ⭐         (LÃI SUẤT & TIỀN TẾ weekly)  ← SKILL NÀY
vn-research-dashboard       (render HTML equity research — share _viz-shared/)
```

## Tham khảo

- **`references/sources_overview.md`** — ⭐ 3 PDF + 7 upstream sources, URL patterns, pitfalls
- **`references/data_cards.md`** — ⭐ 35 chỉ số mapping + 4-week schema + narrative rules + **DANH SÁCH CẤM speculation**
- **`references/rendering.md`** — ⭐ 15 HTML patterns + 3 rates components + placement rule
- **`references/preflight_check.md`** — Tet auto-backfill + retry hints + partial override
- **`assets/weekly_template.html`** — ⭐ HTML template (self-contained, không cần inject.py)
- **`scripts/fetch_sources.py`** — fetch 12 PDFs + FRED/vnstock upstream
- **`scripts/extract_cards.py`** — parse PDF text → `values[]` 4-week + cross-check
- **`scripts/build_report.py`** — assemble report.json từ 4 tuần cache
- **`scripts/build_report_v3.py`** — build report v3 với narrative depth (NARRATIVE_* constants)
- **`scripts/build_report_v4.py`** — build report v4 hybrid (verbatim + synthesis)
- **`scripts/prose_extractor.py`** — trích 66+ đoạn prose theo topic từ 3 PDF
- **`scripts/hybrid_prose.py`** — trích verbatim dài + ghép với narrative_v2 theo section
- **`scripts/verify_data.py`** — ⭐ **BẮT BUỘC** — re-parse độc lập + đối chiếu report.json vs source (45 điểm)
- **`scripts/render_polished.py`** — render report polished (narrative liền mạch + charts/tables, 0 operational language)
- **`scripts/render_history.py`** — render report history-telling (4 tuần tabs — hạ tầng kỹ thuật, không show user)
- **`scripts/render_report.py`** — fill template v1 từ report.json
- **`scripts/qa_weekly.js`** — Playwright QA (visual checks)
- **`tests/test_extract_cards.py`** — pytest 20 tests (9 parsers + 11 verify)
- **`audit_report.md`** (output) — báo cáo tường minh audit sau mỗi lần chạy

## Pitfalls thực tế — Lessons Learned (BẮT BUỘC đọc trước khi edit)

### Nhóm 1: HTML Structure (nghiêm trọng nhất — vỡ layout toàn bộ)

| # | Lỗi | Triệu chứng | Phòng |
|---|---|---|---|
| 1 | **Thiếu `</section>`** | Click tab nào cũng trống, `getBoundingClientRect` = 0×0 | Sau mỗi edit: kiểm tra `<section>` count = `</section>` count |
| 2 | **Content leak sang section sai** | Chart/hint hiện trong tab khác | Insert **bên trong** section, trước `</section>` — KHÔNG insert giữa `</section>` và `<section>` |
| 3 | **Re-render ghi đè inject** | Thay đổi biến mất sau re-render | Tất cả inject nằm TRONG render script, KHÔNG post-process |

### Nhóm 2: Parser

| # | Lỗi | Phòng |
|---|---|---|
| 4 | **Substring match** ("5 năm" match "15 năm") | Exact match `cells[0].strip() == vn_tenor` |
| 5 | **VN-format decimal** (dot vs comma) | Port `_parse_vietnamese_float` từ Bond Lab |
| 6 | **HTML entity encoding** (HNX `&#224;`) | `html.unescape()` trước parse |
| 7 | **Missing data thật** (SBV thiếu 9M W25) | `spanGaps: true` trong Chart.js |

### Nhóm 3: Data Accuracy

| # | Lỗi | Phòng |
|---|---|---|
| 8 | **Coverage quá thấp** (5%) | Hybrid: cluster agent + cross-week synthesis |
| 9 | **Speculation** ("chốt lời") | Danh sách cấm trong `data_cards.md` |
| 10 | **Bỏ sót số trọng yếu** | Audit coverage ≥80% trước publish |

### Nhóm 4: Design

| # | Lỗi | Phòng |
|---|---|---|
| 11 | **Fork template → Frankenstein** | Viết template mới, không fork nguyên xi |
| 12 | **Operational language** ("W23", "cluster") | Grep = 0 trước publish |
| 13 | **Canvas không render trong hidden tab** | Lazy render khi tab click |
| 14 | **Hint sai lệch data** ("dao động quanh 0" khi thực tế −7 đến +2) | Hint phải lấy số từ chart data thực, verify match |
| 15 | **Hint chỉ định nghĩa chung chung** ("Dương = curve bình thường") | Hint phải nói: ý nghĩa kinh tế + giá trị hiện tại ngầm chỉ điều gì + bất thường so với chuẩn |

### Nhóm 5: Chart Hints — Rules (BẮT BUỘC)

Mỗi chart phải có hint **sau** chart (không trước), với 3 lớp nội dung:

#### Rule 1: Hint phải khớp data thực
- Lấy min/max/latest từ chart dataset
- Viết hint dựa trên số thực, KHÔNG viết chung chung ("dao động quanh 0")
- Nếu data thay đổi → hint phải tự cập nhật (tham chiếu từ chart data)

#### Rule 2: 3 lớp nội dung mỗi hint
1. **Ý nghĩa kinh tế**: chỉ số này đo gì, dương/âm có ý nghĩa gì
2. **Giá trị hiện tại ngầm chỉ điều gì**: latest value → tín hiệu thị trường cụ thể
3. **Bất thường / so sánh**: so với bình thường / so với quốc tế / so với kỳ trước

#### Rule 3: Vị trí
- Hint nằm **SAU** chart (không trước) — người đọc nhìn chart trước, rồi đọc giải thích
- Tránh gây đọc sai: nếu hint nói "dao động quanh 0" mà chart hiện biên độ rộng → sai lệch

#### Ví dụ hint đúng (3 lớp)
```
Độ lồi (convexity):
[1] Ý nghĩa: 2×5 năm − 2 năm − 10 năm đo độ cong đoạn giữa. Dương = curve cong lên (premium rủi ro dài hạn). Âm = lõm (concave).
[2] Giá trị hiện tại: dao động −7 đến +2 bp, chủ yếu âm, hiện −5 bp.
[3] Bất thường: lồi âm bất thường → thiếu cầu đoạn giữa, phù hợp trúng thầu 5 năm thấp (26%) so 10 năm (27%) và 30 năm (48%).
```

#### Ví dụ hint SAI (thiếu ý nghĩa)
```
❌ "Độ lồi dao động quanh 0" — sai data (thực tế chủ yếu âm), thiếu ý nghĩa kinh tế
❌ "Dương = curve bình thường" — chỉ định nghĩa, không nói giá trị hiện tại ngầm chỉ gì
```

### Checklist trước publish (BẮT BUỘC)
```bash
# 1. HTML structure
python3 -c "import re; h=open('report.html').read(); print(f'div={h.count(\"<div\")-h.count(\"</div>\")} sec={h.count(\"<section\")-h.count(\"</section>\")}')" 
# → phải = div=0 sec=0

# 2. JS syntax
node --check /tmp/r.js

# 3. Operational language = 0
grep -cE "W23|W24|W25|W26|cluster|agent|verbatim" report.html  # → phải = 0

# 4. Section visibility (Playwright)
# Mỗi section active phải có getBoundingClientRect().width > 0

# 5. Content position
# Mỗi chart nằm đúng section (section.contains(canvas))
```
