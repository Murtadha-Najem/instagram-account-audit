"""Write sections/99_appendix.md (every post in date order, its numbers and a one-line summary) and post_index.md (the
same list with full digests, the date and topic every writer copies when citing a post).

usage: python appendix.py <username>
"""
import json
import sys

from build_report import Report

HEAD = {"ar": ("ملحق: كل المنشورات", "بالترتيب الزمني. المؤشر النسبي: 1.0 أداء عادي في وقته. المشاهدات للريلز فقط.",
               "| # | التاريخ | المنشور | الشكل | الموضوع | المشاهدات | الإعجابات | التعليقات | المؤشر | ملخص |"),
        "en": ("Appendix: every post", "In date order. Lift: 1.0 is typical for its time. Plays for reels only.",
               "| # | date | post | format | topic | plays | likes | comments | lift | summary |")}


def main():
    rep = Report(sys.argv[1].lstrip("@").lower())
    rows = json.loads((rep.A / "dataset.json").read_text(encoding="utf-8"))
    title, note, head = HEAD.get(rep.lang, HEAD["en"])
    out = [f"## {title}", "", note, "", head, "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        c = r.get("coding") or (r.get("craft") or {}).get("basics") or {}
        digest = (c.get("digest") or "").replace("|", "،" if rep.lang == "ar" else ",").replace("\n", " ")
        short = digest.split(".")[0][:110]
        out.append(f"| {i} | {rep.date(r['posted'][:10])} | {r['shortcode']} | {rep.ar(c.get('format') or r['type'])} | {rep.ar(c.get('topic') or '')} | "
                   f"{format(r['plays'], ',') if r['plays'] else ''} | {r['likes'] if r['likes'] is not None else ''} | {r['comments'] or 0} | "
                   f"{r['perf_lift'] if r['perf_lift'] is not None else ''} | {short} |")
    idx = ["# Post index: cite a post as its topic, date and ID", "",
           "| ID | date | type | format | topic | plays | likes | comments | lift | digest |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r.get("coding") or (r.get("craft") or {}).get("basics") or {}
        idx.append(f"| {r['shortcode']} | {rep.date(r['posted'][:10])} | {rep.ar(r['type'])} | {rep.ar(c.get('format') or '')} | "
                   f"{rep.ar(c.get('topic') or '')} | {r['plays'] or ''} | {r['likes'] if r['likes'] is not None else ''} | {r['comments'] or 0} | "
                   f"{r['perf_lift'] if r['perf_lift'] is not None else ('too recent' if r.get('too_recent') else '')} | "
                   f"{(c.get('digest') or '').replace('|', '/').replace(chr(10), ' ')} |")
    (rep.A / "post_index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    (rep.A / "sections").mkdir(exist_ok=True)
    (rep.A / "sections" / "99_appendix.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"appendix: {len(rows)} rows")


if __name__ == "__main__":
    main()
