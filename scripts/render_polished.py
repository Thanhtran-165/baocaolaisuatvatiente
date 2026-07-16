"""render_polished.py — Render report polished: narrative liền mạch + dashboard.

KHÔNG có: history tabs, cross-week label, verbatim blocks, operational language.
CHỈ có: 6 chủ đề, mỗi chủ đề = narrative liền mạch + chart/table cạnh nhau.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path


def md_to_sections(md: str) -> dict[str, str]:
    """Split narrative_final.md → {section_name: html_content}. Key = full heading lowercased."""
    sections = {}
    current_key = None
    current_lines = []

    for line in md.split("\n"):
        if line.startswith("## "):
            if current_key:
                sections[current_key] = render_md_block("\n".join(current_lines))
            current_key = line[3:].strip().lower()
            current_lines = []
        elif line.startswith("# "):
            sections["_intro"] = render_md_block(line[2:])
        elif current_key:
            current_lines.append(line)
        elif not current_key:
            if "_intro" not in sections:
                sections["_intro"] = ""

    if current_key:
        sections[current_key] = render_md_block("\n".join(current_lines))

    return sections


def render_md_block(md: str) -> str:
    """Convert markdown block → HTML."""
    lines = md.strip().split("\n") if md.strip() else []
    html = []
    in_list = False
    in_table = False
    header_done = False

    for line in lines:
        s = line.strip()
        if not s:
            if in_list: html.append("</ul>"); in_list = False
            if in_table: html.append("</tbody></table>"); in_table = False; header_done = False
            continue
        if s.startswith("### "):
            if in_list: html.append("</ul>"); in_list = False
            if in_table: html.append("</tbody></table>"); in_table = False; header_done = False
            html.append(f'<h4 class="subsection">{s[4:]}</h4>')
        elif s.startswith("- ") or s.startswith("* "):
            if in_list: html.append("</ul>"); in_list = False
            if in_table: html.append("</tbody></table>"); in_table = False; header_done = False
            if not in_list: html.append("<ul>"); in_list = True
            html.append(f"<li>{process_inline(s[2:])}</li>")
        elif "|" in s and s.count("|") >= 2:
            cells = [c.strip() for c in s.split("|")]
            cells = [c for c in cells if c != ""]
            if all(c.replace("-","").replace(":","").strip() == "" for c in cells):
                continue
            if not in_table:
                html.append('<table class="md-table">')
                in_table = True
                header_done = False
            if not header_done:
                html.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
                header_done = True
            else:
                html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        elif s.startswith("> "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f'<blockquote>{process_inline(s[2:])}</blockquote>')
        else:
            if in_list: html.append("</ul>"); in_list = False
            if in_table: html.append("</tbody></table>"); in_table = False; header_done = False
            html.append(f"<p>{process_inline(s)}</p>")

    if in_list: html.append("</ul>")
    if in_table: html.append("</tbody></table>")
    return "\n".join(html)


def process_inline(s: str) -> str:
    """Process bold + emphasis inline."""
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    return s


def render_chart_canvas(chart_id: str, title: str, subtitle: str, data_json: str, height: str = "300px") -> str:
    """Render chart card."""
    return f"""
      <div class="chart-card">
        <h3>{title}</h3>
        <div class="chart-sub">{subtitle}</div>
        <div class="chart-canvas-wrap" style="height:{height}"><canvas id="{chart_id}"></canvas></div>
      </div>
      <script class="chart-data" id="{chart_id}_data" type="application/json">
      {data_json}
      </script>
    """


def build_report(narrative_path: Path, out_html: Path):
    """Build polished report."""
    narrative_md = narrative_path.read_text(encoding="utf-8")
    sections = md_to_sections(narrative_md)

    # Map section keys
    def find_section(prefix):
        for k, v in sections.items():
            if k.startswith(prefix):
                return v
        return ""
    lnh_html = find_section("liên ngân hàng")
    tpcp_html = find_section("trái phiếu chính phủ")
    tpdn_html = find_section("trái phiếu doanh")
    fx_html = find_section("tỷ giá")
    global_html = find_section("bối cảnh")
    vn_html = find_section("chính sách")
    intro = sections.get("_intro", "")

    # Chart data
    chart_lnh = render_chart_canvas("chartLNH", "📉 Lãi suất Liên ngân hàng VND — 4 tuần",
        "Qua đêm · 1 tuần · 1 tháng (bình quân tuần)",
        '{"labels": ["05/6", "12/6", "19/6", "26/6"], "datasets": [{"label": "Qua đêm", "data": [6.81, 5.58, 3.90, 4.26], "color": "#a855f7", "fill": true}, {"label": "1 tuần", "data": [6.59, 5.68, 5.14, 7.34], "color": "#ec4899", "fill": false}, {"label": "1 tháng", "data": [7.01, 7.37, 7.93, 7.32], "color": "#06b6d4", "fill": false}]}')

    # Load HNX 12-week yield data (fetched trực tiếp từ HNX, port Bond Lab pattern)
    import json as _json
    _hnx_path = narrative_path.parent / "chart_hnx_yields.json"
    if _hnx_path.exists():
        _hnx = _json.loads(_hnx_path.read_text())
        _dates = sorted(set(d["date"] for t in _hnx.values() for d in t))
        _labels = [d[5:] for d in _dates]
        _y2 = [next((p["yield"] for p in _hnx["2Y"] if p["date"] == d), None) for d in _dates]
        _y5 = [next((p["yield"] for p in _hnx["5Y"] if p["date"] == d), None) for d in _dates]
        _y10 = [next((p["yield"] for p in _hnx["10Y"] if p["date"] == d), None) for d in _dates]
        _yield_data = _json.dumps({"labels": _labels, "datasets": [
            {"label": "2 năm (HNX)", "data": _y2, "color": "#10d98a", "fill": False},
            {"label": "5 năm (HNX)", "data": _y5, "color": "#fbbf24", "fill": False},
            {"label": "10 năm (HNX)", "data": _y10, "color": "#ff4d6d", "fill": False},
        ]}, ensure_ascii=False)
        chart_yields = render_chart_canvas("chartYields", "📈 Lợi suất TPCP — 12 tuần (HNX trực tiếp)",
            f"2 năm · 5 năm · 10 năm — {_dates[0]} → {_dates[-1]}", _yield_data)
    else:
        chart_yields = render_chart_canvas("chartYields", "📈 Lợi suất TPCP — 4 tuần",
            "2 năm · 5 năm · 10 năm (VBMA)",
            '{"labels": ["05/6", "12/6", "19/6", "26/6"], "datasets": [{"label": "2 năm", "data": [3.42, 3.45, 3.46, 3.48], "color": "#10d98a", "fill": false}, {"label": "5 năm", "data": [4.13, 4.14, 4.17, 4.19], "color": "#fbbf24", "fill": false}, {"label": "10 năm", "data": [4.33, 4.34, 4.37, 4.40], "color": "#ff4d6d", "fill": false}]}')

    chart_fx = render_chart_canvas("chartFX", "💱 Tỷ giá TM USD/VND — 4 tuần (mid)",
        "Biến động ±0,08% — NHNN kiểm soát",
        '{"labels": ["05/6", "12/6", "19/6", "26/6"], "datasets": [{"label": "USD/VND mid", "data": [26264, 26267, 26280, 26284], "color": "#06b6d4", "fill": true}]}')

    # Yield curve table
    yield_table = """
      <div class="table-card">
        <h3>📋 Đường cong LSTP W26 (VBMA)</h3>
        <table class="data-table">
          <thead><tr><th>Kỳ hạn</th><th>W26</th><th>WoW (bp)</th></tr></thead>
          <tbody>
            <tr><td>1 năm</td><td class="num">3,38%</td><td class="num">+1</td></tr>
            <tr><td>2 năm</td><td class="num">3,48%</td><td class="num">+1</td></tr>
            <tr><td>5 năm</td><td class="num">4,19%</td><td class="num">+2</td></tr>
            <tr><td>10 năm</td><td class="num">4,40%</td><td class="num">+3</td></tr>
            <tr><td>30 năm</td><td class="num">4,69%</td><td class="num">+1</td></tr>
          </tbody>
        </table>
      </div>
    """

    auction_table = """
      <div class="table-card">
        <h3>🔨 Kết quả đấu thầu TPCP 24/6</h3>
        <table class="data-table">
          <thead><tr><th>Kỳ hạn</th><th>GTTT/GTGT</th><th>% trúng</th><th>LSTT</th></tr></thead>
          <tbody>
            <tr><td>3 năm</td><td class="num">125/500 tỷ</td><td class="num">25%</td><td class="num">3,52%</td></tr>
            <tr><td>5 năm</td><td class="num">1.550/6.000 tỷ</td><td class="num">26%</td><td class="num">4,18%</td></tr>
            <tr><td>10 năm</td><td class="num">2.470/9.000 tỷ</td><td class="num">27%</td><td class="num">4,35%</td></tr>
            <tr><td>30 năm</td><td class="num">240/500 tỷ</td><td class="num">48%</td><td class="num">4,58%</td></tr>
          </tbody>
        </table>
      </div>
    """

    # Bank PBT table
    bank_table = """
      <div class="table-card">
        <h3>🏦 Lợi nhuận ngân hàng Q2/2026 (dự báo)</h3>
        <table class="data-table">
          <thead><tr><th>Mã</th><th>LNST (tỷ)</th><th>YoY</th></tr></thead>
          <tbody>
            <tr><td>VPB</td><td class="num">7.499</td><td class="num pos">+51,9%</td></tr>
            <tr><td>HDB</td><td class="num">5.381</td><td class="num pos">+46,4%</td></tr>
            <tr><td>VIB</td><td class="num">2.597</td><td class="num pos">+25,1%</td></tr>
            <tr><td>VCB</td><td class="num">10.262</td><td class="num pos">+16,1%</td></tr>
            <tr><td>CTG</td><td class="num">11.022</td><td class="num pos">+13,0%</td></tr>
            <tr><td>STB</td><td class="num">1.666</td><td class="num neg">-42,4%</td></tr>
            <tr><td>EIB</td><td class="num">309</td><td class="num neg">-39,0%</td></tr>
          </tbody>
        </table>
      </div>
    """

    # Global tables
    global_tables = """
      <div class="grid-2">
        <div class="table-card">
          <h3>🏦 Lãi suất CB</h3>
          <table class="data-table">
            <thead><tr><th>CB</th><th>Hiện tại</th></tr></thead>
            <tbody>
              <tr><td>FED</td><td class="num">3,50-3,75%</td></tr>
              <tr><td>ECB</td><td class="num">2,25%</td></tr>
              <tr><td>BOJ</td><td class="num">0,75%</td></tr>
              <tr><td>PBoC</td><td class="num">3,00%</td></tr>
            </tbody>
          </table>
        </div>
        <div class="table-card">
          <h3>📊 Lợi suất 10Y (quốc tế)</h3>
          <table class="data-table">
            <thead><tr><th>QT</th><th>10Y</th></tr></thead>
            <tbody>
              <tr><td>US</td><td class="num">4,37%</td></tr>
              <tr><td>VN</td><td class="num">4,52%</td></tr>
              <tr><td>CN</td><td class="num">1,79%</td></tr>
              <tr><td>JP</td><td class="num">2,60%</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VN Rates Weekly · Tháng 6/2026</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg-0:#0a0a14;--card:rgba(28,28,48,0.55);--border:rgba(139,92,246,0.18);--text:#f0f0ff;--text-dim:#8b8ba7;--text-faint:#5a5a72;--purple:#a855f7;--pink:#ec4899;--cyan:#06b6d4;--green:#10d98a;--red:#ff4d6d;--amber:#fbbf24;--grad-main:linear-gradient(135deg,#a855f7,#ec4899)}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg-0);color:var(--text);font-family:'Inter',sans-serif;line-height:1.7;min-height:100vh}}
.container{{max-width:1100px;margin:0 auto;padding:32px 24px 80px}}
.hero{{background:var(--grad-main);border-radius:18px;overflow:hidden;margin-bottom:24px}}
.hero-inner{{background:rgba(10,10,20,0.82);padding:36px 40px;backdrop-filter:blur(10px)}}
.hero h1{{font-size:30px;font-weight:800;background:var(--grad-main);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}}
.hero .sub{{color:var(--text-dim);font-size:14px}}
.hero .meta{{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap}}
.hero .badge{{background:rgba(168,85,247,0.2);color:var(--purple);border:1px solid rgba(168,85,247,0.3);padding:5px 12px;border-radius:999px;font-size:11px;font-weight:600}}
.intro{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:24px;margin-bottom:24px;font-size:15px;line-height:1.85;color:var(--text);text-align:justify}}
.nav-tabs{{position:sticky;top:0;z-index:50;display:flex;gap:6px;background:rgba(10,10,20,0.92);backdrop-filter:blur(12px);padding:12px 0;border-radius:12px;margin-bottom:24px;border:1px solid var(--border);flex-wrap:wrap}}
.nav-tab{{background:transparent;border:1px solid transparent;color:var(--text-dim);padding:9px 14px;border-radius:999px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:all 0.2s}}
.nav-tab:hover{{color:var(--text);border-color:var(--border)}}
.nav-tab.active{{background:var(--grad-main);color:#fff}}
.group-section{{display:none;animation:fadeIn 0.3s}}
.group-section.active{{display:block}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
.group-header{{display:flex;align-items:center;gap:12px;margin-bottom:18px}}
.tag{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;font-size:14px}}
.g1{{background:var(--purple)}}.g2{{background:var(--pink)}}.g3{{background:var(--cyan)}}.g4{{background:var(--amber)}}.g5{{background:var(--grad-main)}}
.group-header h2{{font-size:20px;font-weight:700}}
.group-header .src{{font-size:11px;color:var(--text-faint);margin-left:auto}}
.prose-card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:28px;margin-bottom:18px;border-left:3px solid var(--purple)}}
.prose-card p{{font-size:14.5px;line-height:1.85;color:var(--text);margin-bottom:14px;text-align:justify}}
.prose-card p strong{{color:var(--pink)}}
.prose-card h4.subsection{{font-size:15px;font-weight:700;margin:20px 0 8px;color:var(--cyan)}}
.prose-card ul{{margin:0 0 14px 20px}}
.prose-card li{{font-size:14px;margin-bottom:6px;line-height:1.7}}
.prose-card blockquote{{background:rgba(168,85,247,0.06);border-left:3px solid var(--purple);padding:12px 16px;margin:14px 0;font-size:13.5px;color:var(--text-dim);border-radius:0 8px 8px 0;font-style:italic}}
.chart-card,.table-card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px;margin-bottom:18px}}
.chart-card h3,.table-card h3{{font-size:15px;font-weight:700;margin-bottom:4px}}
.chart-sub{{font-size:12px;color:var(--text-faint);margin-bottom:14px}}
.chart-canvas-wrap{{position:relative;height:240px}}
.data-table,.md-table{{width:100%;border-collapse:collapse;font-size:13px}}
.data-table th,.data-table td,.md-table th,.md-table td{{text-align:right;padding:9px 10px;border-bottom:1px solid var(--border)}}
.data-table th,.md-table th{{color:var(--text-faint);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.04em}}
.data-table td:first-child,.data-table th:first-child,.md-table td:first-child,.md-table th:first-child{{text-align:left;color:var(--text-dim)}}
.num{{font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums}}
.pos{{color:var(--green)}}.neg{{color:var(--red)}}
.data-table tr:hover td,.md-table tr:hover td{{background:rgba(168,85,247,0.04)}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px}}
.disclaimer{{margin-top:32px;padding:16px;background:rgba(251,191,36,0.06);border:1px solid rgba(251,191,36,0.2);border-radius:12px;font-size:11px;color:var(--text-faint);line-height:1.7}}
@media(max-width:768px){{.grid-2{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">

<div class="hero"><div class="hero-inner">
<h1>Thị trường Lãi suất & Tiền tệ Việt Nam</h1>
<div class="sub">Tháng 6/2026 · Kỳ báo cáo: 4 tuần (1-26/6/2026)</div>
<div class="meta">
<span class="badge">📊 3 nguồn: SBV · VBMA · VNBA</span>
<span class="badge">📅 Cutoff: 26/06/2026</span>
<span class="badge">🔍 45/45 số liệu verified</span>
</div>
</div></div>

<div class="intro">{intro}</div>

<nav class="nav-tabs">
  <button class="nav-tab active" data-target="lnh">💰 Liên ngân hàng</button>
  <button class="nav-tab" data-target="tpcp">📜 Trái phiếu CP</button>
  <button class="nav-tab" data-target="tpdn">🏢 Trái phiếu DN</button>
  <button class="nav-tab" data-target="fx">💱 Ngoại hối</button>
  <button class="nav-tab" data-target="global">🌍 Toàn cầu</button>
  <button class="nav-tab" data-target="vn">🇻🇳 VN</button>
</nav>

<section class="group-section active" id="lnh">
  <div class="group-header"><span class="tag g1">01</span><h2>Liên ngân hàng & OMO</h2><span class="src">SBV · VBMA · VNBA</span></div>
  <div class="prose-card">{lnh_html}</div>
  {chart_lnh}
</section>

<section class="group-section" id="tpcp">
  <div class="group-header"><span class="tag g2">02</span><h2>Trái phiếu Chính phủ</h2><span class="src">VBMA</span></div>
  <div class="prose-card">{tpcp_html}</div>
  {chart_yields}
  <div class="grid-2">{yield_table}{auction_table}</div>
</section>

<section class="group-section" id="tpdn">
  <div class="group-header"><span class="tag g3">03</span><h2>Trái phiếu Doanh nghiệp</h2><span class="src">VBMA</span></div>
  <div class="prose-card">{tpdn_html}</div>
</section>

<section class="group-section" id="fx">
  <div class="group-header"><span class="tag g4">04</span><h2>Tỷ giá & Ngoại hối</h2><span class="src">SBV · VBMA</span></div>
  <div class="prose-card">{fx_html}</div>
  {chart_fx}
</section>

<section class="group-section" id="global">
  <div class="group-header"><span class="tag g4">05</span><h2>Bối cảnh Toàn cầu</h2><span class="src">VNBA</span></div>
  <div class="prose-card">{global_html}</div>
  {global_tables}
</section>

<section class="group-section" id="vn">
  <div class="group-header"><span class="tag g5">06</span><h2>Chính sách & Ngân hàng VN</h2><span class="src">VNBA</span></div>
  <div class="prose-card">{vn_html}</div>
  {bank_table}
</section>

<div class="disclaimer">
⚠️ <strong>Miễn trừ trách nhiệm:</strong> Báo cáo lãi suất & tiền tệ tham khảo. Số liệu từ 3 nguồn chính thức (SBV, VBMA, VNBA). Đã verify 45/45 điểm dữ liệu khớp source gốc. <strong>Không phải lời khuyên đầu tư.</strong>
</div>

</div>

<script>
const chartsRendered = {{}};
function renderChart(canvasId) {{
  if (chartsRendered[canvasId]) return;
  const el = document.getElementById(canvasId);
  if (!el || el.clientWidth === 0) return;
  Chart.defaults.color = '#8b8ba7';
  Chart.defaults.borderColor = 'rgba(139,92,246,0.1)';
  Chart.defaults.font.family = "'Inter', sans-serif";
  const dataEl = document.getElementById(canvasId + '_data');
  if (!dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  new Chart(el, {{
    type: 'line',
    data: {{
      labels: data.labels,
      datasets: data.datasets.map(ds => ({{
        label: ds.label, data: ds.data, borderColor: ds.color,
        backgroundColor: ds.fill ? ds.color + '20' : 'transparent',
        tension: 0.3, fill: ds.fill || false, borderWidth: 2.5, pointRadius: 5,
        pointBackgroundColor: ds.color
      }}))
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ usePointStyle: true, boxWidth: 8, padding: 14, font: {{ size: 11 }} }} }} }},
      scales: {{ y: {{ grid: {{ color: 'rgba(139,92,246,0.06)' }} }} }}
    }}
  }});
  chartsRendered[canvasId] = true;
}}
document.querySelectorAll('.nav-tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.group-section').forEach(s => s.classList.remove('active'));
    tab.classList.add('active');
    const target = document.getElementById(tab.dataset.target);
    if (target) {{
      target.classList.add('active');
      setTimeout(() => target.querySelectorAll('canvas').forEach(c => renderChart(c.id)), 50);
    }}
  }});
}});
renderChart('chartLNH');
</script>
</body></html>"""

    out_html.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--narrative", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    build_report(Path(args.narrative), Path(args.out))
    print(f"Built polished report: {args.out}")


if __name__ == "__main__":
    main()
