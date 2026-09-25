"""Assemble a profile's repost report into a PDF.

usage: python build_pdf.py <profile dir>

Sections come from <profile>/sections/*.md in name order; a file with several "## " headings becomes several
sections. A line holding only [[chart:NAME]] becomes an SVG chart drawn from dataset.json. The introduction, the
limits and the appendix (every post) are generated here. Two passes through headless Edge put page numbers in the
contents page; page numbers are stamped with PyMuPDF.
"""
import html
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import fitz
import markdown

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from taxonomy import EMO_AR, GROUP_AR, GROUP_COLOR, GROUPS, LANG_AR, WEEKDAYS, date_ar, month_label  # noqa: E402

CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))


def esc(s):
    return html.escape(str(s))


# ---------- charts ----------

def svg(w, h, body):
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Segoe UI, Tahoma" font-size="11" style="direction:ltr">{body}</svg>')


def vbars(labels, values, color="#5B7DB1", h=230, fmt=str, highlight=None):
    w, left, bottom, top = 720, 30, 42, 18
    n, vmax = len(values), max(values or [1]) or 1
    bw = (w - left - 10) / max(n, 1)
    out = []
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = left + i * bw
        bh = (h - bottom - top) * v / vmax
        c = (highlight or {}).get(i, color)
        out.append(f'<rect x="{x + bw * 0.15:.1f}" y="{h - bottom - bh:.1f}" width="{bw * 0.7:.1f}" height="{bh:.1f}" fill="{c}" rx="2"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{h - bottom - bh - 4:.1f}" text-anchor="middle" fill="#333">{fmt(v)}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{h - bottom + 16:.1f}" text-anchor="middle" fill="#555" font-size="10">{esc(lab)}</text>')
    out.append(f'<line x1="{left}" x2="{w - 10}" y1="{h - bottom}" y2="{h - bottom}" stroke="#bbb"/>')
    return svg(w, h, "".join(out))


def hbars(labels, values, color="#5B7DB1", total=None, colors=None):
    w, rowh, label_w = 720, 24, 170
    h = rowh * len(values) + 10
    vmax = max(values or [1]) or 1
    out = []
    for i, (lab, v) in enumerate(zip(labels, values)):
        y = 5 + i * rowh
        bw = (w - label_w - 90) * v / vmax
        c = colors[i] if colors else color
        out.append(f'<text x="{w - 5}" y="{y + 16}" text-anchor="end" fill="#333">{esc(lab)}</text>')
        out.append(f'<rect x="{w - label_w - bw:.1f}" y="{y + 4}" width="{bw:.1f}" height="{rowh - 8}" fill="{c}" rx="2"/>')
        share = f" ({100 * v / total:.0f}%)" if total else ""
        out.append(f'<text x="{w - label_w - bw - 6:.1f}" y="{y + 16}" text-anchor="end" fill="#333">{v}{share}</text>')
    return svg(w, h, "".join(out))


def stacked(row_labels, row_counts, keys, key_labels, key_colors):
    w, rowh, label_w, legend_h = 720, 30, 150, 26
    h = rowh * len(row_labels) + legend_h + 10
    out = []
    for i, (lab, counts) in enumerate(zip(row_labels, row_counts)):
        y = legend_h + i * rowh
        total = sum(counts.values()) or 1
        x = w - label_w
        out.append(f'<text x="{w - 5}" y="{y + 19}" text-anchor="end" fill="#333">{esc(lab)} ({sum(counts.values())})</text>')
        for k in keys:
            part = (w - label_w - 10) * counts.get(k, 0) / total
            if part <= 0:
                continue
            x -= part
            out.append(f'<rect x="{x:.1f}" y="{y + 5}" width="{part:.1f}" height="{rowh - 10}" fill="{key_colors[k]}"/>')
            if part > 26:
                out.append(f'<text x="{x + part / 2:.1f}" y="{y + 19}" text-anchor="middle" fill="#fff" font-size="10">{100 * counts.get(k, 0) / total:.0f}%</text>')
    lx = w - 5
    for k in keys:
        lab = key_labels[k]
        out.append(f'<rect x="{lx - 12}" y="6" width="12" height="12" fill="{key_colors[k]}"/>')
        out.append(f'<text x="{lx - 16}" y="16" text-anchor="end" fill="#333" font-size="10">{esc(lab)}</text>')
        lx -= 26 + 7.0 * len(lab)
    return svg(w, h, "".join(out))


def heatmap(rows):
    w, h, left, top = 720, 230, 70, 22
    cw, ch = (w - left - 10) / 24, (h - top - 10) / 7
    grid = Counter((r["repost_weekday"], r["repost_hour"]) for r in rows if r["repost_hour"] is not None)
    vmax = max(grid.values() or [1])
    out = [f'<text x="{w - 10 - (hr + 0.5) * cw:.1f}" y="15" text-anchor="middle" font-size="9" fill="#555">{hr}</text>' for hr in range(24)]
    for i, (d, dar) in enumerate(WEEKDAYS):
        y = top + i * ch
        out.append(f'<text x="{left - 6}" y="{y + ch / 2 + 4:.1f}" text-anchor="end" fill="#333">{dar}</text>')
        for hr in range(24):
            v = grid.get((d, hr), 0)
            a = v / vmax
            out.append(f'<rect x="{w - 10 - (hr + 1) * cw:.1f}" y="{y:.1f}" width="{cw - 1:.1f}" height="{ch - 1:.1f}" fill="rgba(192,80,77,{0.07 + 0.93 * a:.2f})"/>')
            if v:
                out.append(f'<text x="{w - 10 - (hr + 0.5) * cw:.1f}" y="{y + ch / 2 + 4:.1f}" text-anchor="middle" font-size="9" fill="{"#fff" if a > 0.5 else "#333"}">{v}</text>')
    return svg(w, h, "".join(out))


def charts(rows, profile, periods, joined_month):
    c = {}
    months = sorted({r["month"] for r in rows})
    c["months"] = vbars([month_label(m) for m in months], [sum(1 for r in rows if r["month"] == m) for m in months],
                        highlight={i: "#C0504D" for i, m in enumerate(months) if joined_month and m >= joined_month})
    timed = [r for r in rows if r["repost_hour"] is not None]
    if timed:
        c["hours"] = vbars([str(h) for h in range(24)], [sum(1 for r in timed if r["repost_hour"] == h) for h in range(24)], color="#8064A2", h=200)
        c["heatmap"] = heatmap(timed)
        lags = [r["lag_days"] for r in timed if r["lag_days"] is not None]
        buckets = [("أقل من 6 ساعات", 0, .25), ("6 إلى 24 ساعة", .25, 1), ("1 إلى 3 أيام", 1, 3), ("3 إلى 7 أيام", 3, 7), ("أسبوع إلى شهر", 7, 30), ("أكثر من شهر", 30, 1e9)]
        c["lag"] = hbars([b[0] for b in buckets], [sum(1 for x in lags if lo < x <= hi or (lo == 0 and x <= hi)) for _, lo, hi in buckets], color="#4BACC6", total=len(lags))
    g = Counter(r["group"] for r in rows).most_common()
    c["groups"] = hbars([GROUP_AR[k] for k, _ in g], [v for _, v in g], total=len(rows), colors=[GROUP_COLOR[k] for k, _ in g])
    names = [x["name"] for x in periods]
    c["groups_period"] = stacked(names, [Counter(r["group"] for r in rows if r["period"] == p) for p in names], list(GROUPS), GROUP_AR, GROUP_COLOR)
    c["groups_month"] = stacked([month_label(m) for m in months], [Counter(r["group"] for r in rows if r["month"] == m) for m in months], list(GROUPS), GROUP_AR, GROUP_COLOR)
    top_langs = [k for k, _ in Counter(r["c_language"] for r in rows).most_common(7)]
    palette = ["#5B7DB1", "#8064A2", "#C0504D", "#E0A43A", "#4E9A6B", "#4BACC6", "#9C8468", "#aaaaaa"]
    keys = top_langs + ["_rest"]
    c["language_period"] = stacked(names, [Counter(r["c_language"] if r["c_language"] in top_langs else "_rest" for r in rows if r["period"] == p) for p in names],
                                   keys, {**LANG_AR, "_rest": "غيرها"}, dict(zip(keys, palette)))
    e = Counter(r["c_emotion"] for r in rows).most_common()
    c["emotions"] = hbars([EMO_AR.get(k, k) for k, _ in e], [v for _, v in e], color="#C0504D", total=len(rows))
    if profile.get("viewer_is_target"):
        c["reactions_month"] = vbars([month_label(m) for m in months],
                                     [round(sum(len(r.get("reactions") or []) for r in rows if r["month"] == m) / max(1, sum(1 for r in rows if r["month"] == m)), 1) for m in months],
                                     color="#4E9A6B", fmt=lambda v: f"{v:g}")
        rg = sorted(((k, round(sum(len(r.get("reactions") or []) for r in rows if r["group"] == k) / n, 2)) for k in GROUPS
                     if (n := sum(1 for r in rows if r["group"] == k))), key=lambda kv: -kv[1])
        c["reactions_group"] = hbars([GROUP_AR[k] for k, _ in rg], [v for _, v in rg], colors=[GROUP_COLOR[k] for k, _ in rg])
        c["follows_group"] = stacked([GROUP_AR[k] for k in GROUPS if any(r["group"] == k for r in rows)],
                                     [{"yes": sum(1 for r in rows if r["group"] == k and r.get("follows_owner")),
                                       "no": sum(1 for r in rows if r["group"] == k and not r.get("follows_owner"))} for k in GROUPS if any(r["group"] == k for r in rows)],
                                     ["yes", "no"], {"yes": "حساب يتابعه", "no": "حساب ما يتابعه"}, {"yes": "#4E9A6B", "no": "#cccccc"})
    return c


# ---------- text ----------

LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s")
HANDLE_RE = re.compile(r"(?<![\w/@])@[A-Za-z0-9_.]*[A-Za-z0-9_]")
TOKEN_WITH_UNDERSCORE = re.compile(r"(?<![\w\\])[A-Za-z0-9.@]*_[A-Za-z0-9_.]*")


def prepare_markdown(md):
    """Blank line before lists, four-space nesting, and escaped underscores inside handles."""
    out = []
    for line in md.splitlines():
        m = LIST_ITEM.match(line)
        if m:
            indent = len(m.group(1))
            if indent:
                line = " " * (4 * max(1, (indent + 2) // 4)) + line.lstrip()  # 2 to 5 spaces is one level
            prev = out[-1] if out else ""
            if prev.strip() and not LIST_ITEM.match(prev) and not prev.startswith((" ", "\t")):
                out.append("")
        if "[[chart:" not in line and not line.lstrip().startswith("<"):
            line = TOKEN_WITH_UNDERSCORE.sub(lambda t: t.group(0).replace("_", r"\_"), line)
        out.append(line)
    return "\n".join(out)


def split_sections(md):
    parts = re.split(r"(?m)^(?=## )", md)
    return [x for x in parts if x.strip().startswith("## ")] or ([md] if md.strip() else [])


def intro_md(rows, profile, own):
    you = "إنت" if own else "صاحب الحساب"
    timed = [r for r in rows if r["repost_utc"]]
    span = f"من {date_ar(timed[0]['repost_date'])} إلى {date_ar(timed[-1]['repost_date'])}" if timed else "بترتيب شبكة الريبوستات"
    notes = sum(1 for r in rows if r["note"])
    return f"""## قبل ما تبدي: شنو هذا التقرير

هذا تحليل لكل ريبوست على حساب @{profile['username']} {span}: {len(rows)} منشور من أصل {profile.get('reposts')} انجمعت. ما أكو منشور محسوب بدون ما ينشاف، وبالملحق جدول بيه كلها بالتسلسل.

<div class="kpis">
<div class="kpi"><b>{len(rows)}</b><span>ريبوست محلل</span></div>
<div class="kpi"><b>{len({r['owner'] for r in rows})}</b><span>حساب مختلف</span></div>
<div class="kpi"><b>{len({r['repost_date'] for r in timed})}</b><span>يوم نشر</span></div>
<div class="kpi"><b>{notes}</b><span>ملاحظة كتبها {you}</span></div>
</div>

### شلون انبنى
1. **انجمعت الريبوستات من انستغرام مباشرة، ويا الرد الخام لكل منشور.** الرد الخام بيه وقت الريبوست والملاحظة، وتفاصيل الأغنية، والأرقام.{' وبما إن الحساب حسابك، بيه كذلك منو تفاعل ويا ريبوستك، ومنو عاد نشره.' if own else ''}
2. **كل منشور انحلل محلياً:** الموسيقى (نموذج صوتي، وعلامة انستغرام أو Shazam)، والكلام (تفريغ حرفي)، والنص على الشاشة (OCR)، والصورة (ملخص مشاهد وإطارات حسب الحاجة).
3. **كل منشور انشاف ووصفه كاتب واحد بنفس المرور،** وطلع منه وصف كامل وتصنيف على 20 بُعد: الموضوع، الشكل، اللغة، العاطفة، النبرة، النكتة، القيم، ولمن موجّه.
4. **الأقسام انكتبت من هاي المواد**، وكل رقم وكل مثال راجع لمنشور معين.

**أي جملة تبدي بـ "قراءة:" هي استنتاج مبني على الدليل اللي قبلها، مو حقيقة مؤكدة.**
"""


def limits_md(rows, profile, own):
    timed = sum(1 for r in rows if r["repost_utc"])
    who = "إنت" if own else "صاحب الحساب"
    lines = [
        "## حدود هذا التحليل",
        "",
        "**شنو ما يشوف:**",
        f"- الريبوستات اللي انحذفت قبل الجمع ({profile.get('collected_at_utc')} UTC)، والستوريات والتعليقات والرسائل.",
        "- الريبوست اختيار من اللي عرضته الخوارزمية.",
        "",
        "**الأغنية والكابشن:** يختارهم صاحب المنشور، مو اللي عاد نشره.",
        "",
        "**تحفظات على البيانات:**",
        "- التصنيف سوّاه نموذج على وصف مكتوب، ولكل منشور موضوع رئيسي واحد.",
        f"- وقت الريبوست معروف لـ {timed} من {len(rows)} منشور."
        + ("" if timed == len(rows) else " الباقي مرتب حسب شبكة الريبوستات، وتاريخه تقريبي حسب تاريخ نشر المنشور الأصلي."),
        "- المراحل اللي بيها منشورات قليلة، نسبها تتأرجح بسهولة.",
    ]
    if not own:
        lines.append(f"- الحساب مو حساب اللي شغّل التحليل، فتفاعل متابعين {who} مو ظاهر، والتحليل يوصف نمط المحتوى بدون افتراضات عن الدين أو الصحة أو العلاقات.")
    lines.append('- كل جملة تبدي بـ "قراءة:" تفسير قابل للخطأ.')
    return "\n".join(lines) + "\n"


def appendix(rows, own):
    head = "<th>#</th><th>الوقت</th><th>الحساب</th><th>المنشور</th><th>المجموعة</th><th>العاطفة</th>" + ("<th>تفاعل</th>" if own else "") + "<th>الملاحظة</th>"
    out = ['<h2>ملحق: كل الريبوستات بالتسلسل</h2>', f'<table class="appendix"><thead><tr>{head}</tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        out.append(f'<tr><td>{i}</td><td class="nowrap">{esc(r["repost_local"] or "~" + r["month"])}</td><td class="acct">@{esc(r["owner"])}</td>'
                   f'<td>{esc(r["title"])}</td><td><span class="dot" style="background:{GROUP_COLOR[r["group"]]}"></span>{GROUP_AR[r["group"]]}</td>'
                   f'<td>{EMO_AR.get(r["c_emotion"], r["c_emotion"])}</td>' + (f'<td>{len(r.get("reactions") or [])}</td>' if own else "")
                   + f'<td>{esc(r["note"])}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
html { direction: rtl; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 10.6pt; line-height: 1.85; color: #222; }
h1 { font-size: 30pt; margin: 0; color: #2b2b2b; }
h2 { font-size: 19pt; color: #2b3f63; border-bottom: 2px solid #2b3f63; padding-bottom: 4px; margin-top: 0; break-before: page; }
h3 { font-size: 13.5pt; color: #7a2e2c; margin: 20px 0 6px; break-after: avoid; }
h4 { font-size: 11.5pt; margin: 14px 0 4px; break-after: avoid; }
p { margin: 6px 0 9px; text-align: justify; }
ul, ol { margin: 4px 0 10px; padding-right: 22px; padding-left: 0; }
li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 14px; font-size: 9.3pt; line-height: 1.5; }
th { background: #2b3f63; color: #fff; font-weight: 600; padding: 5px 6px; text-align: right; }
td { border-bottom: 1px solid #e2e2e2; padding: 4px 6px; vertical-align: top; }
tr:nth-child(even) td { background: #f6f7fa; }
tr { break-inside: avoid; }
bdi { unicode-bidi: isolate; }
.chart { display: block; margin: 10px 0 4px; break-inside: avoid; }
.caption { font-size: 9pt; color: #666; margin: 0 0 14px; text-align: center; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; }
.cover .sub { font-size: 14pt; color: #555; margin-top: 12px; }
.cover .meta { margin-top: 60px; font-size: 11pt; color: #444; line-height: 2; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 12px 0 18px; }
.kpi { background: #f3f5f9; border-radius: 6px; padding: 8px 10px; break-inside: avoid; }
.kpi b { display: block; font-size: 17pt; color: #2b3f63; line-height: 1.3; }
.kpi span { font-size: 9pt; color: #555; }
.toc { list-style: none; padding: 0; font-size: 12pt; }
.toc li { display: flex; border-bottom: 1px dotted #bbb; padding: 5px 0; }
.toc li span.t { flex: 1; }
.marker { font-size: 1pt; color: #fff; }
table.appendix { font-size: 7.8pt; }
table.appendix td { padding: 3px 4px; }
.nowrap { white-space: nowrap; }
.acct { direction: ltr; text-align: right; white-space: nowrap; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-left: 4px; }
"""


def build_html(p, toc_pages):
    profile = json.loads((p / "profile.json").read_text(encoding="utf-8"))
    rows = json.loads((p / "dataset.json").read_text(encoding="utf-8"))
    context = json.loads((p / "context.json").read_text(encoding="utf-8")) if (p / "context.json").exists() else {}
    own = bool(profile.get("viewer_is_target"))
    periods = context.get("periods") or [{"name": x} for x in dict.fromkeys(r["period"] for r in rows)]
    chart_svgs = charts(rows, profile, periods, context.get("highlight_from_month"))
    texts = [intro_md(rows, profile, own)]
    for f in sorted((p / "sections").glob("*.md")):
        texts += split_sections(f.read_text(encoding="utf-8"))
    texts.append(limits_md(rows, profile, own))
    bodies, titles = [], []
    for i, md in enumerate(texts):
        titles.append(re.search(r"^## (.+)$", md, re.M).group(1).strip())
        body = markdown.markdown(prepare_markdown(md), extensions=["tables", "sane_lists"])
        body = re.sub(r"<p>\[\[chart:(\w+)\]\]</p>", lambda m: chart_svgs.get(m.group(1), ""), body)
        body = HANDLE_RE.sub(lambda m: f"<bdi>{m.group(0)}</bdi>", body)
        bodies.append(body.replace("</h2>", f'<span class="marker">SECMARK{i:02d}</span></h2>', 1))
    titles.append("ملحق: كل الريبوستات بالتسلسل")
    app = appendix(rows, own).replace("</h2>", f'<span class="marker">SECMARK{len(titles) - 1:02d}</span></h2>', 1)
    toc = "".join(f'<li><span class="t">{esc(t)}</span><span>{toc_pages.get(i, "")}</span></li>' for i, t in enumerate(titles))
    timed = [r for r in rows if r["repost_date"]]
    span = f"{date_ar(timed[0]['repost_date'])} إلى {date_ar(timed[-1]['repost_date'])}" if timed else ""
    cover = (f'<div class="cover"><h1>ريبوستات <bdi>@{esc(profile["username"])}</bdi></h1><div class="sub">تحليل مفصل لـ {len(rows)} ريبوست</div>'
             f'<div class="sub">{span}</div><div class="meta">{esc(profile.get("full_name") or "")}<br>أُعد في {date_ar(datetime.now().strftime('%Y-%m-%d'))}</div></div>'
             f'<h2 style="border:none">المحتويات</h2><ul class="toc">{toc}</ul>')
    doc = (f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>ريبوستات @{esc(profile['username'])}</title>"
           f"<style>{CSS}</style></head><body>{cover}{''.join(bodies)}{app}</body></html>")
    return doc, len(titles)


def render(p, doc, pdf_path):
    html_path = p / "report.html"
    html_path.write_text(doc, encoding="utf-8")
    Path(pdf_path).unlink(missing_ok=True)  # otherwise the wait below would accept the previous pass's file
    for attempt in range(3):
        subprocess.run([CONFIG["edge"], "--headless", "--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
                        f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True, capture_output=True, timeout=600)
        for _ in range(30):  # Edge sometimes returns before the file is on disk, and sometimes writes nothing at all
            if Path(pdf_path).exists():
                return
            time.sleep(1)
        print(f"  Edge produced no PDF (attempt {attempt + 1}), retrying", flush=True)
    raise RuntimeError(f"Edge did not write {pdf_path}")


def markers(pdf_path, n):
    doc = fitz.open(pdf_path)
    pages = {}
    for pno, page in enumerate(doc, 1):
        text = page.get_text()
        for i in range(n):
            if i not in pages and f"SECMARK{i:02d}" in text:
                pages[i] = pno
    doc.close()
    return pages


SHORT_CSS = """
h2 { break-before: auto; margin-top: 18px; font-size: 16pt; }
h2:first-of-type { margin-top: 0; }
body { font-size: 10.2pt; line-height: 1.7; }
.head { border-bottom: 3px solid #2b3f63; padding-bottom: 8px; margin-bottom: 12px; }
.head h1 { font-size: 22pt; }
.head .sub { color: #555; font-size: 10.5pt; }
"""


def build_short(p, pdf_path):
    """A 3 to 5 page brief from <profile>/short.md: no cover, contents, intro, limits or appendix."""
    profile = json.loads((p / "profile.json").read_text(encoding="utf-8"))
    rows = json.loads((p / "dataset.json").read_text(encoding="utf-8"))
    context = json.loads((p / "context.json").read_text(encoding="utf-8")) if (p / "context.json").exists() else {}
    periods = context.get("periods") or [{"name": x} for x in dict.fromkeys(r["period"] for r in rows)]
    chart_svgs = charts(rows, profile, periods, context.get("highlight_from_month"))
    body = markdown.markdown(prepare_markdown((p / "short.md").read_text(encoding="utf-8")), extensions=["tables", "sane_lists"])
    body = re.sub(r"<p>\[\[chart:(\w+)\]\]</p>", lambda m: chart_svgs.get(m.group(1), ""), body)
    body = HANDLE_RE.sub(lambda m: f"<bdi>{m.group(0)}</bdi>", body)
    timed = [r for r in rows if r["repost_date"]]
    span = f"{date_ar(timed[0]['repost_date'])} إلى {date_ar(timed[-1]['repost_date'])}" if timed else ""
    head = (f'<div class="head"><h1>ريبوستات <bdi>@{esc(profile["username"])}</bdi></h1>'
            f'<div class="sub">تحليل لـ {len(rows)} ريبوست، {span}. أُعد في {date_ar(datetime.now().strftime("%Y-%m-%d"))}</div></div>')
    doc = (f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>ريبوستات @{esc(profile['username'])}</title>"
           f"<style>{CSS}{SHORT_CSS}</style></head><body>{head}{body}</body></html>")
    tmp = p / "_short.pdf"
    render(p, doc, tmp)
    out = fitz.open(tmp)
    for pno, page in enumerate(out, 1):
        page.insert_text((page.rect.width / 2 - 6, page.rect.height - 22), str(pno), fontsize=9, color=(0.4, 0.4, 0.4))
    out.save(pdf_path)
    count = out.page_count
    out.close()
    tmp.unlink()
    print(f"{pdf_path}: {count} pages (short)")


def main():
    p = Path(sys.argv[1]).resolve()
    if "--short" in sys.argv:
        build_short(p, p / "report_short.pdf")
        return
    tmp, final = p / "_pass.pdf", p / "report.pdf"
    doc, n = build_html(p, {})
    render(p, doc, tmp)
    pages = markers(tmp, n)
    doc, _ = build_html(p, pages)
    render(p, doc, tmp)
    out = fitz.open(tmp)
    for pno, page in enumerate(out, 1):
        if pno > 1:
            page.insert_text((page.rect.width / 2 - 6, page.rect.height - 22), str(pno), fontsize=9, color=(0.4, 0.4, 0.4))
    out.save(final)
    count = out.page_count
    out.close()
    tmp.unlink()
    print(f"{final}: {count} pages, {n} sections")


if __name__ == "__main__":
    main()
