# Sources Overview — vn-rates-weekly

3 nguồn PDF weekly chính thức + 7 upstream sources (portable, không gọi API local).

## Lớp 1 — 3 PDF weekly (snapshot 4 tuần × 3 nguồn = 12 PDFs / chạy)

### 1. SBV bulletin — "Diễn biến TT ngoại tệ & LNH tuần"
- **Role**: Chính thức, hẹp (monetary hẹp)
- **Scope**: LNH (ON/1W/2W/1M), tỷ giá trung tâm + TM, OMO
- **Article URL**: `sbv.gov.vn/vi/web/sbv_portal/w/diễn-biến-...-tuần-từ-{D1}-{D2}.{M}.{YYYY}` (slug tiếng Việt có dấu, URL-encode)
- **PDF URL**: `/documents/20117/0/{D1}-{D2}.{M}.{YYYY}.pdf/{uuid}?t=...` — UUID bắt buộc, phải scrape từ article
- **Fetch**: `curl` article → regex `<embed src>` → `curl` PDF → `pdftotext -layout`
- **Pitfalls**:
  - WAF "Request Rejected" (F5 BIG-IP) khi request dồn dập → add `Referer` + `Accept-Language: vi`, sleep 3s
  - Tuần lễ Tết → SBV skip → auto-backfill tuần trước, flag `tet_skip`
  - URL slug có dấu tiếng Việt — phải URL-encode đúng (không strip dấu)

### 2. VBMA báo cáo tuần — "Bản tin TT trái phiếu tuần"
- **Role**: Chuyên sâu trái phiếu
- **Scope**: LSTP (2Y/5Y/10Y), auction TPCP, secondary, TPDN phát hành, foreign holdings
- **Listing URL**: `vbma.org.vn/vi/reports/weekly?page=1` (12 hrefs gần nhất, direct-download)
- **PDF URL**: `vbma.org.vn/storage/reports/{MonthEn}{Year}/{DDMMYYYY}-{DDMMYYYY} BAO CAO TUAN TTP[N].pdf`
- **Fetch**: `curl` listing → regex 4 hrefs → `curl` PDF (%20 encode spaces) → `pdftotext`
- **Pitfalls**:
  - **`www.vbma.org.vn` → HTTP 526 SSL error** → dùng bare domain `vbma.org.vn`
  - Filename spacing non-deterministic: `TTTP` / `TTTP1` / `TTTP2` / double space → LUÔN scrape href chính xác, KHÔNG construct URL
  - Folder `{MonthEn}{Year}` = tháng publish (không phải tuần báo), e.g. tuần 22-26/6 filed dưới `July2026`

### 3. VNBA bản tin tuần — "Bản tin KT-TC-TT tuần N tháng M"
- **Role**: Rộng nhất, bối cảnh toàn cảnh
- **Scope**: Global (Fed/ECB/BOJ, gold/oil/DXY/US rates), VN macro + monetary + bonds + equities + bank PBT quý
- **Article URL**: `vnba.org.vn/vi/ban-tin-kinh-te-tai-chinh-tien-te-tuan-{N}-thang-{M}-{YYYY}-{id}.htm`
- **Archive**: `/vi/hashtag/kinh-te-tai-chinh-tien-te-tuan-{1..5}` (1 hashtag per week-of-month)
- **CDN PDF**: `s-vnba-cdn.aicms.vn/vnba-media/26/{M}/{DD}/{slug}_{hash}.pdf?md5=...&expires=...`
- **Fetch**: `curl` hashtag → regex article → `curl` article → regex CDN PDF → `curl` PDF → `pdftotext`
- **Pitfalls**:
  - CDN md5/expires token **hiện không enforce** (test: wrong md5 / past expiry / no token → vẫn 200) nhưng re-fetch defensive
  - Monthly variant "tuần 1 tháng M+1" xen vào → filter theo `data_cutoff`, chỉ giữ weekly
  - Article id monotonic nhưng không 1:1 với tuần (content khác cũng tiêu thụ id)

## Lớp 2 — Upstream headline (12 tuần cho card Type A)

Gọi trực tiếp upstream (KHÔNG qua API local :8001):

| Source | Endpoint | Granularity | Backfill | Chart cho |
|---|---|---|---|---|
| HNX yield curve | `POST hnx.vn/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData` (`pDate`) | Daily | ✅ từ 2014-01-02 | LSTP 2Y/5Y/10Y |
| HNX auction | `POST hnx.vn/ModuleReportBonds/Bond_DauThau/Bond_KetQua_DauThau` (range) | Weekly | ✅ từ 2013-01-01 | Auction |
| HNX FTP PDF | `GET owa.hnx.vn/ftp/.../TP/{date}_TP_Yield_change_statistics.pdf` | Daily | ✅ từ 2013-01-01 | Yield change |
| SBV interbank | `GET sbv.gov.vn/lãi-suất1` (HTML) | Daily (latest-only) | ❌ accumulate | LNH cross-check |
| FRED | `GET api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=...` | Daily | ✅ decades | US 10Y/2Y, DXY (cần `FRED_API_KEY`) |
| ABO | `GET asianbondsonline.adb.org/vietnam/` | Daily (latest-only) | ❌ | Cross-check LSTP |
| vnstock (VCI) | `Quote.history(symbol='VNINDEX', interval='1W')` | Weekly | ✅ | VN-Index |

## Cross-check priority
- **Monetary hẹp**: SBV > VBMA > VNBA
- **Bối cảnh rộng**: VNBA > VBMA
- **LSTP**: HNX raw > VBMA tổng hợp
- Sai số <2% OK, 2-5% flag AMBER, >5% dùng priority source

## Test connectivity (pre-flight)
```bash
# FRED
echo $FRED_API_KEY  # phải set
curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=$FRED_API_KEY&file_type=json&limit=1" | head -c 100

# vnstock
python3 -c "from vnstock.api.quote import Quote; q=Quote(symbol='VNINDEX',source='VCI'); print(q.history(start='2026-06-01',end='2026-06-26',interval='1W').head())"

# HNX
curl -s -X POST "https://hnx.vn/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData" \
  -d "pDate=26/06/2026" | head -c 200
```
