# VN Rates Weekly

Báo cáo tuần thị trường lãi suất & tiền tệ Việt Nam — tự động hoàn toàn từ 3 nguồn chính thức (SBV + VBMA + VNBA) + upstream trực tiếp (HNX + FRED).

## Cài đặt

### Yêu cầu

```bash
# Python 3.11+
python3 --version

# Node.js (cho QA gates)
node --version

# pdftotext (poppler)
brew install poppler        # macOS
# hoặc: apt install poppler-utils  # Ubuntu

# Playwright (cho visual QA)
npm install playwright
```

### FRED API Key (tùy chọn — cho chart US 10Y/DXY)

Đăng ký miễn phí tại: https://fred.stlouisfed.org/docs/api/api_key.html

```bash
export FRED_API_KEY="your_key_here"
```

Không có key → chart US 10Y/DXY sẽ bị skip, báo cáo vẫn hoạt động.

## Chạy

### Lệnh duy nhất

```bash
python3 scripts/run_pipeline.py --week 2026-W27 --out ./output/
```

### Pipeline tự động 7 bước

```
Bước 0: Check deps (pdftotext, node, FRED_API_KEY)
Bước 1: Pre-flight (check sources available)
Bước 2: Fetch PDFs (rolling cache — chỉ fetch tuần mới)
Bước 3: Fetch upstream (HNX yield curve + auction + FRED)
Bước 4: Build report.json (extract + data-driven narrative)
Bước 5: Verify data (45+ points cross-check, exit 1 nếu mismatch)
Bước 6: Render HTML (charts + tables + narrative)
Bước 7: Audit gates (HTML structure + JS + banned words)
```

### Output

```
output/
├── report.html          ← báo cáo cuối (deploy lên Vercel)
├── report.json          ← data structured
├── chart_data.json      ← HNX + FRED chart data
└── sources_cache/       ← rolling cache (giữ 5 tuần)
    ├── sbv_2026-W24.txt
    ├── sbv_2026-W25.txt
    ├── sbv_2026-W26.txt
    ├── sbv_2026-W27.txt
    ├── vbma_W24.txt ... W27.txt
    └── vnba_W24.txt ... W27.txt
```

### Rolling cache (tự động)

| Lần chạy | Fetch | Thời gian |
|---|---|---|
| Lần 1 (tuần mới) | 4 tuần × 3 nguồn = 12 PDFs | ~2 phút |
| Lần 2+ (tuần tiếp theo) | **1 tuần × 3 nguồn = 3 PDFs** | ~30 giây |

Cache giữ 5 tuần (4 dùng + 1 buffer), tự động xóa tuần cũ.

### Deploy

```bash
cp output/report.html deploy/index.html
cd deploy && vercel --prod
```

## Nguồn dữ liệu

| Nguồn | Loại | Cách fetch | Lịch sử |
|---|---|---|---|
| **SBV** | LNH, tỷ giá, OMO | PDF embed → curl + pdftotext | 4 tuần rolling |
| **VBMA** | TPCP yield, auction, TPDN, foreign | PDF listing → curl + pdftotext | 4 tuần rolling |
| **VNBA** | Policy, global macro, bank PBT | Sidebar crawl → CDN PDF | 4 tuần rolling |
| **HNX** | Yield curve 8 tenors, auction 5 tenors | POST API trực tiếp | 12 tuần chart |
| **FRED** | US 10Y, DXY proxy | JSON API trực tiếp | 12 tuần chart |

## Audit gates (tự động)

Pipeline chạy 4 gates trước publish:

1. **HTML structure**: div/section balance = 0
2. **JS syntax**: `node --check` pass
3. **Banned words**: 0 speculation (17 cụm cấm)
4. **Operational language**: 0 (W23/W24/cluster/agent/verbatim)

Nếu bất kỳ gate fail → pipeline exit 1, không publish.

## Verify dữ liệu

Pipeline tự động cross-check:
- SBV bình quân tuần vs VBMA bình quân 5 ngày (Δ ≤ 5 đcb)
- HNX par yield vs VBMA trading yield (Δ ≤ 5 đcb)
- HNX auction win% vs VBMA báo cáo (Δ ≤ 1%)

45+ số liệu verified mỗi lần chạy.

## Cấu trúc skill

```
vn-rates-weekly/
├── SKILL.md                    # Workflow + rules + pitfalls
├── README.md                   # File này
├── scripts/
│   ├── run_pipeline.py         # ⭐ Orchestrator — 1 lệnh
│   ├── audit_gate.py           # 4 QA gates
│   ├── fetch_sources.py        # Fetch SBV+VBMA+VNBA PDFs
│   ├── upstream_fetch.py       # Fetch HNX+FRED trực tiếp
│   ├── extract_cards.py        # Parse PDF text → structured
│   ├── build_report_v2.py      # Build report.json
│   ├── verify_data.py          # Cross-check 45+ points
│   ├── render_report_v2.py     # JSON → HTML
│   └── qa_weekly.js            # Playwright visual QA
├── references/
│   ├── sources_overview.md     # 3 PDF + 2 upstream sources
│   ├── data_cards.md           # 35 indicators + narrative rules
│   ├── rendering.md            # HTML patterns + chart hints
│   └── preflight_check.md      # Tet/holiday + retry logic
└── tests/
    └── test_extract_cards.py   # 20 pytest tests
```

## Lịch publish

| Nguồn | Khi nào publish | Thử lại sau |
|---|---|---|
| SBV | Đầu tuần sau (T2-T3) | — |
| VBMA | T3-T4 tuần sau | — |
| VNBA | T4-T5 tuần sau | Thứ 6 tuần sau |
| HNX/FRED | Real-time | Luôn available |

→ Chạy pipeline sau **thứ 6 tuần N+1** để đảm bảo cả 3 nguồn đã publish.
