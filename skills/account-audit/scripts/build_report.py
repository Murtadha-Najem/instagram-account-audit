"""Assemble the audit report into a PDF, in the account's colours when it has them, and check it before delivery.

usage: python build_report.py <username>
Sections: audit/analysis/sections/*.md in name order; a file with several "## " headings becomes several sections.
In a section:
  [[chart:NAME]]            an SVG chart drawn from dataset.json (names: see CHARTS below; the build lists unknown ones)
  [[img:FILE|caption]]      an exhibit from analysis/img/; consecutive lines sit side by side
  <div class="kpis"><div class="kpi"><b>N</b><span>label</span></div>...</div>   headline numbers
Theme: themes/default.json, overridden by account.json "brand" {"colors": {...}, "logo_light": png for the dark cover,
"logo_dark": png for the page header}. Language and direction from account.json "report_language" (default ar).
After rendering, the build checks: a heading stranded at the bottom of a page, dashes and arrows (house style), a post
ID without a date beside it, an ID that is not in the dataset, and missing charts or images. Fix and rebuild until clean.
"""
import base64
import html
import json
import re
import statistics as st
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import fitz
import markdown

from common import CONFIG, SKILL, account, root

RTL = {"ar", "fa", "ur", "he"}
MONTHS = {"ar": ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]}
MONTHS_SHORT = {"ar": ["ك2", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "ت1", "ت2", "ك1"],
                "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
TEXT = {"ar": {"section": "القسم", "contents": "المحتويات", "kicker": "تقرير تحليلي", "on": "على انستغرام", "posts": "منشوراً",
               "plays": "مشاهدة ريلز", "followers": "متابعاً", "made": "أُعد في", "to": "إلى", "appendix": "ملحق",
               "sub": "تحليل التفاعل والجمهور وصناعة المحتوى", "own": "خاص", "collab": "مشترك"},
        "en": {"section": "Section", "contents": "Contents", "kicker": "Account audit", "on": "on Instagram", "posts": "posts",
               "plays": "reel plays", "followers": "followers", "made": "Prepared", "to": "to", "appendix": "Appendix",
               "sub": "Engagement, audience and content craft", "own": "own", "collab": "collab"}}
HANDLE_RE = re.compile(r"(?<![\w/@])@[A-Za-z0-9_.]*[A-Za-z0-9_]")
UNDERSCORE = re.compile(r"(?<![\w\\])[A-Za-z0-9.@]*_[A-Za-z0-9_.]*")
LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s")
FORBIDDEN = re.compile("[—–→←⇒·•✓✔\U0001F300-\U0001FAFF]")
CODE_RE = re.compile(r"(?<![\w/-])[A-Za-z0-9_-]{11}(?![\w-])")


def esc(s):
    return html.escape(str(s))


class Report:
    def __init__(self, user):
        self.user = user
        self.R = root(user)
        self.A = self.R / "analysis"
        self.acc = account(user)
        self.lang = self.acc.get("report_language", "ar")
        self.T = TEXT.get(self.lang, TEXT["en"])
        theme = json.loads((SKILL / "themes" / "default.json").read_text(encoding="utf-8"))
        brand = self.acc.get("brand") or {}
        theme["colors"].update(brand.get("colors") or {})
        theme.update({k: v for k, v in brand.items() if k in ("logo_light", "logo_dark", "font_latin", "font_arabic")})
        self.theme = theme
        self.C = theme["colors"]
        lf = SKILL / "scripts" / f"labels_{self.lang}.json"
        self.labels = json.loads(lf.read_text(encoding="utf-8")) if lf.exists() else {}
        tax_f = self.A / "taxonomy.json"
        tax = json.loads(tax_f.read_text(encoding="utf-8")) if tax_f.exists() else {}
        for group in ("topics", "formats"):
            for k, v in (tax.get(group) or {}).items():
                if isinstance(v, dict) and v.get("label"):
                    self.labels[k] = v["label"]
        for p in self.acc["team"]:
            if p.get("display"):
                self.labels[p["name"]] = p["display"]
        self.labels.update(self.acc["face_names"])

    def ar(self, v):
        v = str(v)
        return self.labels.get(v, v.replace("_", " "))

    def date(self, d):
        return f"{int(d[8:10])} {MONTHS.get(self.lang, MONTHS['en'])[int(d[5:7]) - 1]} {d[:4]}" if d and len(d) >= 10 else (d or "")

    def month(self, m):
        return f"{MONTHS_SHORT.get(self.lang, MONTHS_SHORT['en'])[int(m[5:7]) - 1]} {m[2:4]}"

    # ---------- charts ----------
    def svg(self, w, h, body):
        return (f'<svg class="chart" viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" '
                f'font-family="{self.theme["font_latin"]}, {self.theme["font_arabic"]}, sans-serif" font-size="11" style="direction:ltr">{body}</svg>')

    def vbars(self, labels, values, color=None, h=230, fmt=str):
        w, left, bottom, top = 720, 30, 42, 18
        n, vmax = len(values), max(values or [1]) or 1
        bw = (w - left - 10) / max(n, 1)
        out = []
        for i, (lab, v) in enumerate(zip(labels, values)):
            x = left + i * bw
            bh = (h - bottom - top) * v / vmax
            out.append(f'<rect x="{x + bw * 0.15:.1f}" y="{h - bottom - bh:.1f}" width="{bw * 0.7:.1f}" height="{bh:.1f}" fill="{color or self.C["ink"]}" rx="2"/>')
            out.append(f'<text x="{x + bw / 2:.1f}" y="{h - bottom - bh - 4:.1f}" text-anchor="middle" fill="#333">{fmt(v)}</text>')
            out.append(f'<text x="{x + bw / 2:.1f}" y="{h - bottom + 16:.1f}" text-anchor="middle" fill="#555" font-size="10">{esc(lab)}</text>')
        out.append(f'<line x1="{left}" x2="{w - 10}" y1="{h - bottom}" y2="{h - bottom}" stroke="#bbb"/>')
        return self.svg(w, h, "".join(out))

    def hbars(self, labels, values, color=None, total=None, colors=None):
        w, rowh, label_w = 720, 24, 190
        h = rowh * len(values) + 10
        vmax = max(values or [1]) or 1
        rtl = self.lang in RTL
        out = []
        for i, (lab, v) in enumerate(zip(labels, values)):
            y = 5 + i * rowh
            bw = (w - label_w - 90) * v / vmax
            c = colors[i] if colors else (color or self.C["ink"])
            share = f" ({100 * v / total:.0f}%)" if total else ""
            if rtl:
                out.append(f'<text x="{w - 5}" y="{y + 16}" text-anchor="end" fill="#333">{esc(lab)}</text>')
                out.append(f'<rect x="{w - label_w - bw:.1f}" y="{y + 4}" width="{bw:.1f}" height="{rowh - 8}" fill="{c}" rx="2"/>')
                out.append(f'<text x="{w - label_w - bw - 6:.1f}" y="{y + 16}" text-anchor="end" fill="#333">{v}{share}</text>')
            else:
                out.append(f'<text x="5" y="{y + 16}" fill="#333">{esc(lab)}</text>')
                out.append(f'<rect x="{label_w}" y="{y + 4}" width="{bw:.1f}" height="{rowh - 8}" fill="{c}" rx="2"/>')
                out.append(f'<text x="{label_w + bw + 6:.1f}" y="{y + 16}" fill="#333">{v}{share}</text>')
        return self.svg(w, h, "".join(out))

    def lift_bars(self, rows, key_fn, min_n=3, top=12):
        groups = {}
        for r in rows:
            for k in key_fn(r) or []:
                if k is not None and k != "":
                    groups.setdefault(str(k), []).append(r.get("perf_lift"))
        items = [(k, st.median([x for x in v if x is not None]), len(v)) for k, v in groups.items()
                 if len(v) >= min_n and any(x is not None for x in v)]
        items.sort(key=lambda x: -x[1])
        items = items[:top]
        vals = [round(m, 2) for _, m, _ in items]
        return self.hbars([f"{self.ar(k)} ({n})" for k, _, n in items], vals,
                          colors=[self.C["accent"] if v >= 1 else self.C["negative"] for v in vals])

    def charts(self, rows):
        c = {}
        cd = lambda r: r.get("coding") or {}  # noqa: E731
        months = sorted({r["month"] for r in rows if r["month"]})
        reels = [r for r in rows if r["type"] == "reel"]
        static = [r for r in rows if r["type"] != "reel"]
        c["monthly_posts"] = self.vbars([self.month(m) for m in months], [sum(1 for r in rows if r["month"] == m) for m in months])
        c["monthly_plays"] = self.vbars([self.month(m) for m in months], [sum(r["plays"] or 0 for r in rows if r["month"] == m) for m in months],
                                        color=self.C["accent"], fmt=lambda v: f"{v / 1000:.1f}K" if v >= 1000 else str(v))
        c["monthly_likes"] = self.vbars([self.month(m) for m in months], [sum(r["likes"] or 0 for r in rows if r["month"] == m) for m in months],
                                        color=self.C["accent2"])
        top = sorted(reels, key=lambda r: -(r["plays"] or 0))[:12]
        c["top_reels"] = self.hbars([f"{self.date(r['posted'][:10])} {r['shortcode']}" for r in top], [r["plays"] or 0 for r in top])
        c["lift_type"] = self.lift_bars(rows, lambda r: [r["type"]], min_n=2)
        c["lift_format"] = self.lift_bars(rows, lambda r: [cd(r).get("format")])
        c["lift_topic"] = self.lift_bars(rows, lambda r: [cd(r).get("topic")])
        c["lift_value"] = self.lift_bars(rows, lambda r: [cd(r).get("value_to_viewer")], min_n=2)
        c["lift_hook"] = self.lift_bars(reels, lambda r: [(cd(r).get("hook") or {}).get("type")], min_n=2)
        c["lift_people"] = self.lift_bars(rows, lambda r: r["people_on_screen"] or ["nobody recognised"], min_n=2)
        c["lift_partner_kind"] = self.lift_bars(rows, lambda r: [r["partner_kind"]], min_n=2)
        c["lift_cta"] = self.lift_bars(rows, lambda r: cd(r).get("cta") or ["none"])
        c["lift_language"] = self.lift_bars(rows, lambda r: [cd(r).get("language")])
        c["lift_textlang_static"] = self.lift_bars(static, lambda r: [cd(r).get("text_language")], min_n=2)
        c["lift_structure"] = self.lift_bars(rows, lambda r: [cd(r).get("structure")], min_n=2)
        c["lift_weekday"] = self.lift_bars(rows, lambda r: [r["weekday"]], min_n=2)
        c["lift_eye_reels"] = self.lift_bars(reels, lambda r: [(cd(r).get("speaking_style") or {}).get("eye_contact")]
                                             if (cd(r).get("speaking_style") or {}).get("applies") else [], min_n=2)
        c["lift_delivery_energy"] = self.lift_bars(reels, lambda r: [f"{(r.get('delivery') or {}).get('energy')}/5"]
                                                   if (r.get("delivery") or {}).get("energy") else [], min_n=2)
        band = lambda h: "00-08" if h < 9 else "09-14" if h < 15 else "15-18" if h < 19 else "19-23"  # noqa: E731
        c["lift_hour"] = self.lift_bars(rows, lambda r: [band(r["hour"])] if r["hour"] is not None else [], min_n=2)
        length = lambda d: "<15s" if d < 15 else "15-30s" if d < 30 else "30-60s" if d < 60 else "60-90s" if d < 90 else "90s+"  # noqa: E731
        c["lift_length"] = self.lift_bars(reels, lambda r: [length(r["duration_s"])] if r["duration_s"] else [], min_n=2)
        hs = {}
        for r in reels:
            k = (cd(r).get("hook") or {}).get("strength")
            if k:
                hs.setdefault(k, []).append(r["perf_lift"])
        ks = sorted(hs)
        c["lift_by_hook_strength"] = self.vbars([f"{k} ({len(hs[k])})" for k in ks],
                                                [round(st.median([x for x in hs[k] if x is not None] or [0]), 2) for k in ks], color=self.C["accent"])
        likes_by = Counter()
        for r in rows:
            f = self.R / "likers" / f"{r['shortcode']}.json"
            if f.exists():
                for u in json.loads(f.read_text(encoding="utf-8"))["likers"]:
                    likes_by[u["username"]] += 1
        bands = [("1", 1, 1), ("2-4", 2, 4), ("5-9", 5, 9), ("10-19", 10, 19), ("20+", 20, 10 ** 6)]
        c["liker_bands_accounts"] = self.vbars([b[0] for b in bands], [sum(1 for v in likes_by.values() if b[1] <= v <= b[2]) for b in bands])
        c["liker_bands_likes"] = self.vbars([b[0] for b in bands], [sum(v for v in likes_by.values() if b[1] <= v <= b[2]) for b in bands], color=self.C["accent"])
        cats = Counter(cc.get("category") for r in rows for cc in (cd(r).get("comments_coded") or []))
        items = cats.most_common(12)
        c["comment_cats"] = self.hbars([self.ar(k) for k, _ in items], [v for _, v in items], total=sum(cats.values()) or None)
        crafted = [r for r in rows if r.get("craft")]
        dims = [("script", "script_score"), ("delivery", "delivery_score"), ("filming", "filming_score"), ("editing", "editing_score"),
                ("design", "design_score"), ("caption", "caption_score")]
        names = {"ar": {"script": "النص", "delivery": "الإلقاء", "filming": "التصوير", "editing": "المونتاج", "design": "التصميم", "caption": "الكابشن"}}
        vals, labs = [], []
        for part, k in dims:
            xs = [(r["craft"].get(part) or {}).get(k) for r in crafted if (r["craft"].get(part) or {}).get("applies", True)]
            xs = [x for x in xs if isinstance(x, (int, float))]
            if xs:
                vals.append(round(sum(xs) / len(xs), 2))
                labs.append(f"{names.get(self.lang, {}).get(part, part)} ({len(xs)})")
        c["craft_scores"] = self.hbars(labs, vals, color=self.C["accent"])
        by = {}
        for r in crafted:
            k = r["craft"].get("craft_score")
            if isinstance(k, (int, float)) and r["perf_lift"] is not None:
                by.setdefault(int(k), []).append(r["perf_lift"])
        c["lift_by_craft_score"] = self.vbars([f"{k} ({len(by[k])})" for k in sorted(by)], [round(st.median(by[k]), 2) for k in sorted(by)], color=self.C["accent"])
        if reels:
            w, h, left, bottom, top_pad = 720, 260, 48, 36, 14
            ts = [datetime.strptime(r["posted"], "%Y-%m-%d %H:%M").timestamp() for r in reels]
            t0, t1 = min(ts), max(ts)
            vmax = max(r["plays"] or 0 for r in reels) or 1
            pts = []
            for r, t in zip(reels, ts):
                x = left + (w - left - 10) * (t - t0) / (t1 - t0 or 1)
                y = h - bottom - (h - bottom - top_pad) * (r["plays"] or 0) / vmax
                pts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{self.C["highlight"] if r["collab"] else self.C["ink"]}" opacity="0.85"/>')
                if (r["plays"] or 0) > vmax * 0.25:
                    pts.append(f'<text x="{x + 7:.1f}" y="{y + 4:.1f}" font-size="9" fill="#333">{r["shortcode"]}</text>')
            for m in months:
                t = datetime.strptime(m + "-01", "%Y-%m-%d").timestamp()
                if t0 <= t <= t1:
                    x = left + (w - left - 10) * (t - t0) / (t1 - t0 or 1)
                    pts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top_pad}" y2="{h - bottom}" stroke="#eee"/>'
                               f'<text x="{x:.1f}" y="{h - bottom + 14}" font-size="9" text-anchor="middle" fill="#666">{self.month(m)}</text>')
            pts.append(f'<line x1="{left}" x2="{w - 10}" y1="{h - bottom}" y2="{h - bottom}" stroke="#bbb"/>')
            pts.append(f'<rect x="{w - 150}" y="4" width="10" height="10" fill="{self.C["ink"]}"/><text x="{w - 136}" y="13" font-size="10">{self.T["own"]}</text>'
                       f'<rect x="{w - 90}" y="4" width="10" height="10" fill="{self.C["highlight"]}"/><text x="{w - 76}" y="13" font-size="10">{self.T["collab"]}</text>')
            c["reels_timeline"] = self.svg(w, h, "".join(pts))
        return c

    # ---------- document ----------
    def css(self):
        C, rtl = self.C, self.lang in RTL
        fonts = self.theme["google_fonts"]
        return f"""
@import url('{fonts}');
:root {{ --ink:{C['ink']}; --accent:{C['accent']}; --accent2:{C['accent2']}; --surface:{C['surface']}; --highlight:{C['highlight']};
  --negative:{C['negative']}; --text:{C['text']}; --soft:{C['soft']}; --line:{C['line']}; --zebra:{C['zebra']}; }}
@page {{ size: A4; margin: 22mm 16mm 20mm 16mm; }}
@page cover {{ size: A4; margin: 0; }}
html {{ direction: {'rtl' if rtl else 'ltr'}; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ margin: 0; font-family: '{self.theme['font_latin']}', '{self.theme['font_arabic']}', sans-serif; font-size: 10.4pt; line-height: {1.9 if rtl else 1.6};
  color: var(--text); }}
strong, b {{ color: var(--ink); font-weight: 700; }}
h1, h2, h3, h4 {{ color: var(--ink); }}
.sec {{ counter-increment: sec; }}
.sec h2 {{ break-before: page; font-size: 22pt; font-weight: 700; line-height: 1.35; margin: 0 0 14px; }}
.sec h2::before {{ content: "{self.T['section']} " counter(sec, decimal-leading-zero); display: block; font-size: 9.5pt; font-weight: 600;
  color: var(--accent); margin-bottom: 2px; }}
.sec h2::after {{ content: ""; display: block; width: 56px; height: 4px; background: var(--accent); border-radius: 2px; margin-top: 10px; }}
h3 {{ font-size: 13.5pt; font-weight: 700; margin: 22px 0 8px; padding-inline-start: 10px; border-inline-start: 4px solid var(--accent); line-height: 1.5; }}
h4 {{ font-size: 11.5pt; margin: 14px 0 4px; }}
p {{ margin: 6px 0 10px; text-align: justify; }}
ul, ol {{ margin: 4px 0 12px; padding-inline-start: 22px; padding-inline-end: 0; }}
li {{ margin: 3px 0; }}
li::marker {{ color: var(--accent); font-weight: 700; }}
table {{ border-collapse: separate; border-spacing: 0; width: 100%; margin: 10px 0 16px; font-size: 9pt; line-height: 1.55;
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
th {{ background: var(--ink); color: #fff; font-weight: 600; padding: 7px 8px; text-align: start; }}
td {{ border-top: 1px solid var(--line); padding: 5px 8px; vertical-align: top; }}
tr:nth-child(even) td {{ background: var(--zebra); }}
bdi {{ unicode-bidi: isolate; }}
.chart {{ display: block; margin: 12px 0 6px; }}
.marker {{ font-size: 1pt; color: #fff; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0 20px; }}
.kpi {{ background: var(--surface); border-radius: 10px; padding: 10px 12px; }}
.kpi b {{ display: block; font-family: '{self.theme['font_latin']}', sans-serif; font-size: 20pt; font-weight: 800; color: var(--ink); line-height: 1.25;
  font-variant-numeric: tabular-nums; }}
.kpi span {{ font-size: 8.6pt; color: var(--soft); line-height: 1.5; display: block; }}
.kpi.accent b {{ color: var(--accent); }}
.cover {{ page: cover; position: relative; width: 210mm; height: 296.5mm; box-sizing: border-box; overflow: hidden;
  background: var(--ink); color: #fff; padding: 26mm 22mm; break-after: page; }}
.cover .logo {{ height: 22mm; display: block; }}
.cover .brandname {{ font-size: 16pt; font-weight: 800; color: #fff; letter-spacing: .02em; }}
.cover .slash {{ position: absolute; bottom: -30mm; {'left' if rtl else 'right'}: 14mm; width: 22mm; height: 170mm; background: var(--accent); transform: skewX(-22deg); }}
.cover .slash.s2 {{ {'left' if rtl else 'right'}: 44mm; background: var(--accent2); opacity: .9; }}
.cover .slash.s3 {{ {'left' if rtl else 'right'}: 74mm; width: 6mm; background: var(--highlight); }}
.cover .kicker {{ margin-top: 38mm; display: inline-block; background: var(--highlight); color: var(--ink); font-weight: 700; font-size: 10pt;
  padding: 3px 12px; border-radius: 99px; }}
.cover h1 {{ color: #fff; font-size: 34pt; font-weight: 700; line-height: 1.3; margin: 14px 0 0; }}
.cover h1 .accent {{ color: var(--accent2); display: block; }}
.cover .sub {{ color: var(--surface); font-size: 13pt; margin-top: 14px; line-height: 1.7; max-width: 150mm; }}
.cover .facts {{ display: flex; gap: 22px; margin-top: 18mm; }}
.cover .fact {{ border-inline-start: 3px solid var(--accent); padding-inline-start: 10px; }}
.cover .fact b {{ display: block; color: #fff; font-size: 20pt; font-weight: 800; }}
.cover .fact span {{ color: var(--surface); font-size: 9pt; }}
.cover .meta {{ position: absolute; bottom: 24mm; {'right' if rtl else 'left'}: 22mm; color: var(--surface); font-size: 10pt; line-height: 1.9; }}
.toc-page h2 {{ font-size: 22pt; font-weight: 700; margin: 0 0 16px; }}
.toc-page h2::after {{ content: ""; display: block; width: 56px; height: 4px; background: var(--accent); border-radius: 2px; margin-top: 10px; }}
.toc {{ list-style: none; padding: 0; margin: 0; font-size: 11.5pt; counter-reset: t; }}
.toc li {{ display: flex; align-items: baseline; gap: 12px; border-bottom: 1px solid var(--line); padding: 8px 0; counter-increment: t; }}
.toc li::before {{ content: counter(t, decimal-leading-zero); font-weight: 700; color: var(--accent); font-size: 10pt; min-width: 22px; }}
.toc li span.t {{ flex: 1; color: var(--ink); font-weight: 500; }}
.toc li span.p {{ font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }}
.note {{ color: var(--soft); font-size: 9.5pt; }}
.keep {{ break-inside: avoid; page-break-inside: avoid; }}
table, p, li, blockquote, figure, .chart, .kpis, .kpi, .figs {{ break-inside: avoid; page-break-inside: avoid; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; }}
p {{ orphans: 4; widows: 4; }}
h2, h3, h4 {{ break-after: avoid; page-break-after: avoid; }}
table.appx {{ font-size: 7.4pt; break-inside: auto; page-break-inside: auto; }}
table.appx td {{ padding: 3px 5px; }}
table.appx td:last-child {{ width: 42%; }}
table.appx td:nth-child(2) {{ white-space: nowrap; }}
.figs {{ display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin: 12px 0 18px; }}
.figs figure {{ width: 31%; margin: 0; }}
.figs img {{ width: 100%; max-height: 330px; object-fit: contain; background: var(--surface); border-radius: 10px;
  box-shadow: 0 1px 2px rgba(0,0,0,.06), 0 6px 18px rgba(0,0,0,.10); }}
.figs figcaption {{ font-size: 8pt; color: var(--text); line-height: 1.5; margin-top: 6px; }}
"""

    def prepare(self, md):
        out, figs = [], []

        def flush():
            if figs:
                out.append('<div class="figs">' + "".join(
                    f'<figure><img src="img/{esc(f)}"><figcaption>{esc(cap)}</figcaption></figure>' for f, cap in figs) + "</div>")
                out.append("")
                figs.clear()
        for line in md.splitlines():
            m = re.match(r"^\s*\[\[img:([^|\]]+)\|?([^\]]*)\]\]\s*$", line)
            if m:
                figs.append((m.group(1).strip(), m.group(2).strip()))
                continue
            flush()
            lm = LIST_ITEM.match(line)
            if lm:
                indent = len(lm.group(1))
                if indent:
                    line = " " * (4 * max(1, (indent + 2) // 4)) + line.lstrip()
                prev = out[-1] if out else ""
                if prev.strip() and not LIST_ITEM.match(prev) and not prev.startswith((" ", "\t")):
                    out.append("")
            if "[[chart:" not in line and not line.lstrip().startswith("<"):
                line = UNDERSCORE.sub(lambda t: t.group(0).replace("_", r"\_"), line)
            out.append(line)
        flush()
        return "\n".join(out)

    @staticmethod
    def keep_together(body):
        from bs4 import BeautifulSoup
        blocks = {"table", "ul", "ol", "div", "svg", "figure"}
        soup = BeautifulSoup(body, "html.parser")
        kids = [k for k in soup.contents if getattr(k, "name", None)]
        i = 0
        while i < len(kids):
            k = kids[i]
            group = None
            if k.name in ("h2", "h3", "h4"):
                group = [k]
                j = i + 1
                while j < len(kids) and kids[j].name == "p" and len(group) < 3:
                    group.append(kids[j])
                    j += 1
                if j < len(kids) and kids[j].name in blocks:
                    group.append(kids[j])
                elif j < len(kids) and kids[j].name == "p" and len(group) == 1:
                    group.append(kids[j])
            elif k.name == "p" and i + 1 < len(kids) and kids[i + 1].name in blocks:
                group = [k, kids[i + 1]]
            if group and len(group) > 1:
                wrap = soup.new_tag("div", attrs={"class": "keep"})
                group[0].insert_before(wrap)
                for g in group:
                    wrap.append(g.extract())
                kids = kids[:i] + [wrap] + kids[i + len(group):]
            i += 1
        return str(soup)

    def data_uri(self, path):
        p = Path(path).expanduser()
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else None

    def build_html(self, rows, toc_pages):
        charts = self.charts(rows)
        self.missing = []
        texts = []
        for f in sorted((self.A / "sections").glob("*.md")):
            texts += [x for x in re.split(r"(?m)^(?=## )", f.read_text(encoding="utf-8")) if x.strip().startswith("## ")]
        bodies, titles = [], []
        for i, md in enumerate(texts):
            titles.append(re.search(r"^## (.+)$", md, re.M).group(1).strip())
            body = markdown.markdown(self.prepare(md), extensions=["tables", "sane_lists"])

            def chart(m):
                if m.group(1) in charts:
                    return charts[m.group(1)]
                self.missing.append(f"chart {m.group(1)}")
                return f"<p>[chart {m.group(1)} missing]</p>"
            body = re.sub(r"<p>\[\[chart:(\w+)\]\]</p>", chart, body)
            for src in re.findall(r'<img src="img/([^"]+)"', body):
                if not (self.A / "img" / src).exists():
                    self.missing.append(f"image {src}")
            body = HANDLE_RE.sub(lambda m: f"<bdi>{m.group(0)}</bdi>", body)
            appendix = titles[-1].startswith(self.T["appendix"])
            if appendix:
                body = body.replace("<table>", '<table class="appx">')
            body = body.replace("</h2>", f'<span class="marker">SECMARK{i:02d}</span></h2>', 1)
            if not appendix:
                body = self.keep_together(body)
            bodies.append('<section class="sec">' + body + "</section>")
        toc = "".join(f'<li><span class="t">{esc(t)}</span><span class="p">{toc_pages.get(i, "")}</span></li>' for i, t in enumerate(titles))
        prof_f = self.R / "profile.json"
        prof = json.loads(prof_f.read_text(encoding="utf-8")) if prof_f.exists() else {}
        name = self.acc.get("display_name") or prof.get("name") or f"@{self.user}"
        plays = sum(r["plays"] or 0 for r in rows if r["type"] == "reel")
        span = f"{self.date(rows[0]['posted'][:10])} {self.T['to']} {self.date(rows[-1]['posted'][:10])}" if rows else ""
        logo = self.data_uri(self.theme["logo_light"]) if self.theme.get("logo_light") else None
        top = f'<img class="logo" src="{logo}">' if logo else f'<div class="brandname"><bdi>@{esc(self.user)}</bdi></div>'
        facts = f'<div class="fact"><b>{len(rows)}</b><span>{self.T["posts"]}</span></div>'
        if plays:
            facts += f'<div class="fact"><b>{plays:,}</b><span>{self.T["plays"]}</span></div>'
        if prof.get("followers"):
            facts += f'<div class="fact"><b>{prof["followers"]:,}</b><span>{self.T["followers"]}</span></div>'
        cover = (f'<div class="cover">{top}<div class="slash"></div><div class="slash s2"></div><div class="slash s3"></div>'
                 f'<div class="kicker">{esc(self.acc.get("report_kicker") or self.T["kicker"])}</div>'
                 f'<h1>{esc(name)}<span class="accent">{self.T["on"]}</span></h1>'
                 f'<div class="sub">{esc(self.acc.get("report_subtitle") or self.T["sub"])}</div><div class="facts">{facts}</div>'
                 f'<div class="meta"><bdi>@{esc(self.user)}</bdi><br>{span}<br>{self.T["made"]} {self.date(datetime.now().strftime("%Y-%m-%d"))}</div></div>'
                 f'<div class="toc-page"><h2>{self.T["contents"]}</h2><ul class="toc">{toc}</ul></div>')
        doc = (f"<!doctype html><html lang='{self.lang}' dir='{'rtl' if self.lang in RTL else 'ltr'}'><head><meta charset='utf-8'>"
               f"<title>{esc(name)}</title><style>{self.css()}</style></head><body>{cover}{''.join(bodies)}</body></html>")
        return doc, len(titles)

    def render(self, doc, pdf):
        page = self.A / "report.html"
        page.write_text(doc, encoding="utf-8")
        Path(pdf).unlink(missing_ok=True)
        for attempt in range(3):
            subprocess.run([CONFIG["edge"], "--headless", "--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
                            f"--print-to-pdf={pdf}", page.as_uri()], check=True, capture_output=True, timeout=900)
            for _ in range(40):
                if Path(pdf).exists():
                    return
                time.sleep(1)
            print(f"  Edge wrote no PDF (attempt {attempt + 1}), retrying", flush=True)
        raise RuntimeError(f"Edge did not write {pdf}")

    @staticmethod
    def markers(pdf, n):
        d = fitz.open(pdf)
        pages = {}
        for pno, page in enumerate(d, 1):
            text = page.get_text()
            for i in range(n):
                if i not in pages and f"SECMARK{i:02d}" in text:
                    pages[i] = pno
        d.close()
        return pages

    def stamp(self, tmp, final):
        out = fitz.open(tmp)
        ink = tuple(int(self.C["ink"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        line = tuple(int(self.C["line"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        logo = Path(self.theme["logo_dark"]).expanduser() if self.theme.get("logo_dark") else None
        for pno, page in enumerate(out, 1):
            if pno == 1:
                continue
            w, h = page.rect.width, page.rect.height
            if logo and logo.exists():
                page.insert_image(fitz.Rect(40, 22, 102, 40.6), filename=str(logo), keep_proportion=True)
            else:
                page.insert_text((40, 38), f"@{self.user}", fontsize=8.5, color=ink)
            page.draw_line(fitz.Point(40, 48), fitz.Point(w - 40, 48), color=line, width=0.6)
            page.insert_text((w / 2 - 6, h - 24), str(pno), fontsize=9, color=ink)
        out.save(final)
        n = out.page_count
        out.close()
        return n

    def check(self, pdf, rows):
        issues = list(self.missing)
        d = fitz.open(pdf)
        for pno, page in enumerate(d, 1):
            if pno <= 2:
                continue
            blocks = [b for b in page.get_text("dict")["blocks"] if b.get("lines")]
            body = [b for b in blocks if 50 < b["bbox"][1] < page.rect.height - 40]
            if not body:
                continue
            last = max(body, key=lambda b: b["bbox"][3])
            size = max(s["size"] for ln in last["lines"] for s in ln["spans"])
            if size >= 12.5 and last["bbox"][3] > page.rect.height * 0.72:
                text = " ".join(s["text"] for ln in last["lines"] for s in ln["spans"])[:60]
                issues.append(f"page {pno}: heading left at the bottom: {text}")
        d.close()
        codes = {r["shortcode"] for r in json.loads((self.A / "dataset.json").read_text(encoding="utf-8"))}
        month_words = "|".join(MONTHS.get(self.lang, MONTHS["en"]) + MONTHS["en"])
        date_re = re.compile(rf"(\d{{1,2}} ({month_words}) \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|({month_words}) \d{{4}})")
        no_dash = self.acc.get("house_style_no_dashes", True)
        for f in sorted((self.A / "sections").glob("*.md")):
            if f.name.startswith("99"):
                continue
            for n, para in enumerate(re.split(r"\n\s*\n", f.read_text(encoding="utf-8")), 1):
                if no_dash:
                    bad = sorted(set(FORBIDDEN.findall(re.sub(r"\|[-:| ]+\|", "", para))))
                    if bad:
                        issues.append(f"{f.name} paragraph {n}: forbidden characters {' '.join(bad)}")
                if para.lstrip().startswith(("|", "<", "[[")):
                    continue
                # an ID has a digit, _ or -, or a capital after its first letter; an ordinary 11-letter word has none
                found = [c for c in CODE_RE.findall(para) if re.search(r"[0-9_-]", c) or re.search(r"[A-Z]", c[1:])]
                for c in found:
                    if c not in codes:
                        issues.append(f"{f.name} paragraph {n}: {c} is not a post in the dataset")
                if any(c in codes for c in found) and not date_re.search(para):
                    issues.append(f"{f.name} paragraph {n}: a post is cited without its date")
        return issues

    def build(self):
        rows = json.loads((self.A / "dataset.json").read_text(encoding="utf-8"))
        rows = [r for r in rows if r["posted"] and not r.get("too_recent")]
        tmp, final = self.A / "_pass.pdf", self.A / "report.pdf"
        doc, n = self.build_html(rows, {})
        self.render(doc, tmp)
        doc, _ = self.build_html(rows, self.markers(tmp, n))
        self.render(doc, tmp)
        pages = self.stamp(tmp, final)
        issues = self.check(tmp, rows)
        tmp.unlink()
        print(f"{final}: {pages} pages, {n} sections")
        print("CHECK: clean" if not issues else "CHECK: " + str(len(issues)) + " issues\n  " + "\n  ".join(issues))


if __name__ == "__main__":
    Report(sys.argv[1].lstrip("@").lower()).build()
