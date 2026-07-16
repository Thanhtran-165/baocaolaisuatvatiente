# Rendering — 15 patterns + 3 rates components + placement rule

## Base template
`assets/weekly_template.html` — fork từ `vn-macro-monthly/assets/report_template.html`.

**Quan trọng**: Template macro là **self-contained** (CSS viết tay inline đầy đủ `.data-card`, `.nav-tabs`, `.hero`, `.kpi`, `.highlight-box`, `.rc-grid`...). KHÔNG migrate sang `_viz-shared/inject.py` — macro template tự styled đẹp rồi. Chỉ thêm rates-specific CSS (`.stance-gauge`, `.wow-strip`) vào cuối `<style>` block.

## Lỗi đã sửa (lesson learned)
Ban đầu cố migrate sang `{{VIZ_CSS}}`/`{{VIZ_JS}}` → inject.py inject JS sai vị trí, mất CSS → dashboard unstyled (body đen, font Times). Fix: giữ nguyên CSS gốc macro, chỉ thêm component rates-specific. **KHÔNG thêm template vào `_viz-shared/inject.py` TEMPLATE_PATHS**.

## Design system `_viz-shared/`
Chia sẻ với mọi VN financial skill:
- `tokens.css` — design tokens (`--purple`, `--green`, `--bg-0`...) + 3 theme (Fintech default / Bloomberg / Corporate)
- `components.css` — `.hero`, `.card`, `.kpi`, `.fin-table`, `.data-card`, `.signal-grid`...
- `viz.js` — `viz.chart()` registry, scrollspy nav, candlestick renderer
- `inject.py` — thay `{{VIZ_CSS}}`/`{{VIZ_JS}}` → single-file output

### Design tokens (giữ cross-skill consistency)
- `--purple:#a855f7`, `--pink:#ec4899`, `--cyan:#06b6d4` — accent + chart
- `--green:#10d98a` = dovish/thuận, `--red:#ff4d6d` = hawkish/thắt chặt, `--amber:#fbbf24` = trung tính
- Font: Inter + JetBrains Mono (`font-variant-numeric: tabular-nums`)
- Theme Corporate cho PDF export

## 15 patterns áp dụng từ các skill

| # | Pattern (nguồn skill) | Áp dụng |
|---|---|---|
| 1 | `inject.py` + `{{VIZ_CSS}}`/`{{VIZ_JS}}` (`_viz-shared`) | Kế thừa design system, tránh copy tay |
| 2 | `.nav-tabs` click-to-switch + placement rule (`vn-macro-monthly`) | 5 tab; mọi component toggleable PHẢI nằm trong `<section class="group-section">` |
| 3 | `data-card` 15-field + `dc-meta` WoW (`vn-macro-monthly`) | Mỗi card có `values[]` 4-week + `wow_pct` + narrative |
| 4 | `mini-table` yield curve/tenor (`vn-macro-monthly`) | Bảng LSTP + LNH theo kỳ hạn với WoW/MoM(đcb) |
| 5 | `highlight-box` pos/neg (`vn-macro-monthly`) | 🔴 Thắt chặt vs 🟢 Thuận ở đầu mỗi tab |
| 6 | `.kpi` strip + `.flag-dot` (`vn-macro-monthly`) | Hero 4 KPI: LSTP 10Y \| LNH ON \| Tỷ giá \| VN-Index |
| 7 | `.rc-grid` risks/catalysts + `.rc-level` (`vn-macro-monthly`) | Tab Tổng hợp |
| 8 | `.kt-list` numbered + ★ (`vn-macro-monthly`) | 3-5 key takeaways tuần |
| 9 | `val-grid` 5-scenario (`vn-research-dashboard`) | "Kịch bản lãi suất" 5 cột, 1 `.base` |
| 10 | `.signal-grid` 6-cell (`vn-technical-analysis`) | 6 tín hiệu hawkish/dovish stance |
| 11 | `.exec-summary` + 4 `exec-hl` (`equity-research-vn`) | Tóm tắt above-the-fold |
| 12 | Sentiment meter + per-category bars (`vn-news-digest`) | "Stance meter" + thanh ngang mỗi kênh |
| 13 | 5-part event card + "Vì sao quan trọng" (`vn-news-digest`) | Sự kiện tuần (NHNN, OMO, đấu thầu) |
| 14 | Vertical timeline `tl-item` (`vn-news-digest`) | Timeline Mon→Fri sự kiện tuần |
| 15 | Coverage-warn banner + `_sources_coverage` (`vn-macro-monthly`) | Partial run warning |

## 3 rates-specific components (mới)

### `.stance-gauge` — gauge HAWKISH↔DOVISH ở hero
```html
<div class="stance-gauge">
  <span class="gauge-label left">HAWKISH</span>
  <div class="gauge-track">
    <div class="gauge-needle" id="stanceNeedle" style="left: 50%;"></div>
  </div>
  <span class="gauge-label right">DOVISH</span>
</div>
```
Needle `left` % = `((stance_score + 6) / 12) * 100` (stance_score -6 hawkish .. +6 dovish).

### `.wow-strip` — thanh 4 ô (W-3..W) + streak badge
```html
<div class="wow-strip">
  <div class="wow-cell"><div class="wow-week">W23</div><div class="wow-val">1.45</div></div>
  <div class="wow-cell"><div class="wow-week">W24</div><div class="wow-val">1.38</div></div>
  <div class="wow-cell"><div class="wow-week">W25</div><div class="wow-val">1.30</div></div>
  <div class="wow-cell latest"><div class="wow-week">W26</div><div class="wow-val">1.20</div></div>
  <div class="streak-badge down">▼ 3 tuần giảm liên tiếp (dovish)</div>
</div>
```
**Rates semantics**: `.streak-badge.up` = red (hawkish), `.down` = green (dovish) — NGƯỢC equity.

### `.curve-chart-inline` — yield curve luôn hiển thị (không modal)
(v1: tái sử dụng `#yieldCurve` canvas có sẵn của macro template)

## Tab placement rule (BẮT BUỘC)
Mọi component muốn ẩn/hiện theo tab → PHẢI nằm trong `<section class="group-section" id="...">`. Chỉ HERO, NAV, FOOTER đặt ngoài (luôn hiện). Rủi ro/Động lực/Takeaways nằm trong group5 (Tổng hợp).

## Render contract — `str.replace`, KHÔNG f-string/.format()
Macro template dùng static demo content (không `{{UPPER}}` tokens). Render qua `str.replace` trên các chuỗi marker cố định. Lý do: JS braces `{}` trong template sẽ break Python f-string/.format().

```python
# ĐÚNG
html = html.replace("⚖️ TRUNG TÍNH", f"⚖️ {verdict}")

# SAI (break JS braces)
html = template.format(verdict=verdict)  # ❌
```

## QA triple-gate (BẮT BUỘC)
1. **JS syntax**: extract last `<script>` → `node --check`
2. **Visual**: Playwright `scripts/qa_weekly.js` (11 checks: hero, 5 tabs, group sections, data cards, wow-strip, tab switch, stance needle, console errors, screenshots)

```bash
NODE_PATH=/tmp/qa-weekly-runner/node_modules node scripts/qa_weekly.js \
  --url=file:///path/to/report.html --output=/tmp/qa-weekly
```
Expected: `✅ PASS: 11`, 0 FAIL.

## CHART HINTS — Rules (BẮT BUỘC)

### Vị trí
- Hint nằm **SAU** chart (không trước) — tránh đọc sai
- Người đọc nhìn biểu đồ trước, rồi đọc giải thích

### 3 lớp nội dung mỗi hint
1. **Ý nghĩa kinh tế**: chỉ số đo gì, dương/âm/dưới mức X có ý nghĩa gì
2. **Giá trị hiện tại ngầm chỉ điều gì**: số thực từ chart → tín hiệu thị trường cụ thể
3. **Bất thường / so sánh**: so với bình thường / quốc tế / kỳ trước

### Hint phải khớp data thực
- Lấy min/max/latest từ chart dataset để viết hint
- KHÔNG viết chung chung ("dao động quanh 0") khi data thực khác
- Ví dụ SAI: "dao động quanh 0" khi convexity thực −7 đến +2
- Ví dụ ĐÚNG: "dao động −7 đến +2 bp, chủ yếu âm → curve hơi lõm"

### Danh sách hints bắt buộc (mỗi chart 1 hint sau)
| Chart | Hint phải nói |
|---|---|
| LNH VND | ON dao động rộng nhất → kỳ hạn nhạy cảm OMO; spread 1W-ON bất thường → căng thẳng thanh khoản |
| Yield curve | Dốc lên (normal) → không suy thoái; curve dịch lên → chi phí vay tăng |
| Spread | Đoạn nào tăng nhiều nhất → steepening/flattening; bear/bull steepening |
| Slope | Dương = không suy thoái; so US (chỉ 20bp) → VN dư địa nới lỏng |
| Convexity | Âm = thiếu cầu đoạn giữa; khớp với trúng thầu thấp ở 5 năm |
