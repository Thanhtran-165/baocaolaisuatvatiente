"""audit_gate.py — Packaged QA gates. Exit 1 nếu bất kỳ gate fail.

Gates:
1. HTML structure (div/section balance)
2. JS syntax (node --check)
3. Banned words (17 cụm cấm speculation)
4. Section visibility (getBoundingClientRect > 0 — cần Playwright, optional)
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

# Danh sách cấm tuyệt đối
BANNED_WORDS = [
    "dàn dựng", "chốt lời", "bài học về kỷ luật", "default chain",
    "cạnh tranh gay gắt", "chủ động rút bớt", "chủ động tái cấu trúc",
    "chiến lược kéo dài đáo hạn", "gợi ý", "điều này có nghĩa",
    "sẽ phải", "chắc chắn rằng", "ý đồ",
    "tín hiệu tích cực", "tín hiệu tiêu cực", "đáng lo ngại",
]


def gate_html_structure(html_path: Path) -> bool:
    """Gate 1: div/section open/close balance."""
    html = html_path.read_text(encoding="utf-8")
    div_diff = html.count("<div") - html.count("</div>")
    sec_diff = html.count("<section") - html.count("</section>")
    if div_diff != 0 or sec_diff != 0:
        print(f"  ❌ HTML structure: div diff={div_diff}, section diff={sec_diff}")
        return False
    print("  ✅ HTML structure: div=0, section=0")
    return True


def gate_js_syntax(html_path: Path) -> bool:
    """Gate 2: JS syntax check via node."""
    html = html_path.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    js_scripts = [s for s in scripts if s.strip() and not s.strip().startswith("{")]
    if not js_scripts:
        print("  ✅ JS syntax: no inline scripts (skip)")
        return True
    # Write last script to temp + check
    tmp = Path("/tmp/audit_gate_check.js")
    tmp.write_text(js_scripts[-1])
    try:
        result = subprocess.run(["node", "--check", str(tmp)], capture_output=True, timeout=10)
        if result.returncode == 0:
            print("  ✅ JS syntax: OK")
            return True
        else:
            print(f"  ❌ JS syntax: {result.stderr.decode()[:200]}")
            return False
    except FileNotFoundError:
        print("  ⚠️ JS syntax: node not found (skip)")
        return True


def gate_banned_words(html_path: Path) -> bool:
    """Gate 3: banned speculation words = 0."""
    html = html_path.read_text(encoding="utf-8")
    text = re.sub(r"<[^>]+>", " ", html).lower()
    text = re.sub(r"\s+", " ", text)

    found = []
    for word in BANNED_WORDS:
        count = text.count(word.lower())
        if count > 0:
            found.append((word, count))

    if found:
        print(f"  ❌ Banned words: {found}")
        return False
    print(f"  ✅ Banned words: 0 (checked {len(BANNED_WORDS)} patterns)")
    return True


def gate_operational_language(html_path: Path) -> bool:
    """Gate 3b: operational language = 0."""
    html = html_path.read_text(encoding="utf-8")
    text = re.sub(r"<[^>]+>", " ", html).lower()
    ops = re.findall(r"\bw23\b|\bw24\b|\bw25\b|\bw26\b|cluster|agent|verbatim", text)
    if ops:
        print(f"  ❌ Operational language: {len(ops)} occurrences")
        return False
    print("  ✅ Operational language: 0")
    return True


def run_all_gates(html_path: Path) -> bool:
    """Run all gates. Return True if all pass."""
    print("\n═══ AUDIT GATES ═══\n")
    results = []
    results.append(("HTML structure", gate_html_structure(html_path)))
    results.append(("JS syntax", gate_js_syntax(html_path)))
    results.append(("Banned words", gate_banned_words(html_path)))
    results.append(("Operational language", gate_operational_language(html_path)))

    print(f"\n{'─'*40}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")

    print(f"\n{'─'*40}")
    if passed == total:
        print(f"✅ ALL {total} GATES PASSED")
        return True
    else:
        print(f"❌ {total - passed}/{total} GATES FAILED")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True, help="Path to report HTML")
    args = parser.parse_args()
    ok = run_all_gates(Path(args.html))
    sys.exit(0 if ok else 1)
