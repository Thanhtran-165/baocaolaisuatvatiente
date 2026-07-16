# Pre-flight Check — All-or-nothing + Tet auto-backfill + partial override

## All-or-nothing (BẮT BUỘC)

Trước khi fetch, kiểm tra 12 PDFs (3 nguồn × 4 tuần) tồn tại + upstream deps:

```
1. Detect tuần N (thứ 2 gần nhất đã kết thúc — thứ 6 tuần trước)
2. Enumerate 4 tuần: [N-3, N-2, N-1, N]
3. Tet/holiday skip check → auto-backfill N-(x+1) nếu cần
4. HEAD check 12 PDFs (3 nguồn × 4 tuần)
5. FRED_API_KEY check (nếu chart Type A)
6. vnstock connectivity check (cho VN-Index chart)
7. 12/12 + deps OK? → fetch | thiếu? → DỪNG + đề xuất tuần thay thế
```

**Quy tắc**: nếu thiếu bất kỳ nguồn → **DỪNG**, không tạo thư mục (máy sạch). Đề xuất ngày thử lại.

## Tet/holiday auto-backfill

Khi tuần x là lễ (SBV skip tuần đó):
- Tự động lấy tuần N-(x+1) thay thế
- Flag `tet_skip: true` trong `report.json` → `period.tet_skipped_weeks: ["2026-W06"]`
- Báo cáo LUÔN đủ 4 điểm dữ liệu

```python
# Logic
weeks = enumerate_4_weeks(target_week)
for w in weeks:
    if is_holiday_week(w):  # check SBV 404 or known Tet calendar
        w_replacement = enumerate_week(w.iso_week_num - 1, with_offset=True)
        report["period"]["tet_skipped_weeks"].append(w.iso_week)
```

Known Tet weeks (âm lịch → dương lịch, tham khảo):
- Tết Nguyên Đán: ~cuối Jan / đầu Feb (varies)
- Giỗ tổ Hùng Vương: ~tháng 4
- 30/4 + 1/5: cuối April / đầu May
- 2/9: đầu September

## Connectivity checks

```bash
# 1. SBV (HTTP 200 = OK)
curl -s -o /dev/null -w "%{http_code}" \
  -H "Referer: https://www.sbv.gov.vn/vi/web/sbv_portal/thong-tin-ve-hoat-dong-ngan-hang-trong-tuan" \
  "https://www.sbv.gov.vn/vi/web/sbv_portal/w/di%E1%BB%85n-bi%E1%BA%BFn-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-ngo%E1%BA%A1i-t%E1%BB%87-v%C3%A0-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-li%C3%AAn-ng%C3%A2n-h%C3%A0ng-tu%E1%BA%A7n-t%E1%BB%AB-22-26.6.2026"
# Expected: 200

# 2. VBMA (HTTP 200)
curl -s -o /dev/null -w "%{http_code}" "https://vbma.org.vn/vi/reports/weekly?page=1"
# Expected: 200 (KHÔNG dùng www. → 526)

# 3. VNBA (HTTP 200)
curl -s -o /dev/null -w "%{http_code}" "https://vnba.org.vn/vi/hashtag/kinh-te-tai-chinh-tien-te-tuan-4"
# Expected: 200

# 4. FRED (optional — nếu no key thì skip upstream US rates)
[ -n "$FRED_API_KEY" ] && echo "FRED OK" || echo "FRED SKIP (no key)"

# 5. vnstock (optional — nếu fail thì VN-Index dùng VNBA PDF Type B)
python3 -c "from vnstock.api.quote import Quote; print('vnstock OK')" 2>/dev/null || echo "vnstock SKIP"
```

## Partial override workflow

User override ("dùng nguồn có sẵn" / "bỏ qua pre-flight") → chạy với nguồn có sẵn:

1. Tạo thư mục + cache NHƯNG chỉ với nguồn có sẵn
2. Áp dụng Nguyên tắc KHÔNG placeholder — KHÔNG tạo card cho chỉ số thiếu nguồn
3. Thêm 1 dòng `coverage-warn` ở hero ghi rõ "X/3 nguồn"
4. Bỏ qua news enrichment nếu partial < 2/3 nguồn
5. Trong `report.json`, thêm field `_sources_coverage`:

```json
"_sources_coverage": {
  "available": ["SBV", "VBMA"],
  "missing": ["VNBA"],
  "user_override": true,
  "retry_hint": "Thử lại sau <date> khi VNBA publish"
}
```

## Khi nào KHÔNG override
- User yêu cầu rõ "đợi đủ 3 nguồn" → mặc định all-or-nothing
- User không nói gì → mặc định all-or-nothing
- Chỉ override khi user explicit: "dùng nguồn có sẵn" / "bỏ qua pre-flight" / tương đương

## Retry hints (lịch publish ước tính)
- SBV: đầu tuần sau (thứ 2-3 tuần N+1)
- VBMA: thứ 3-4 tuần N+1
- VNBA: thứ 4-5 tuần N+1
→ Nếu thiếu tuần N, thử lại sau thứ 6 tuần N+1 (đảm bảo cả 3 đã publish)
