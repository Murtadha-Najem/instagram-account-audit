"""Aggregate the craft reviews: how the posts are written, delivered, shot, edited, designed and captioned, on their own
(scores, distributions, recurring errors) and against performance (lift, and genuine lift where it exists).

usage: python craft_facts.py <username>
writes audit/analysis/craft_facts.md
"""
import json
import statistics as st
import sys
from collections import Counter, defaultdict

from build_dataset import spearman
from common import root

SCORES = [("script", "script_score"), ("script", "concreteness"), ("delivery", "delivery_score"), ("filming", "filming_score"),
          ("filming", "light"), ("editing", "subtitle_legibility"), ("editing", "editing_score"), ("design", "design_score"),
          ("design", "on_brand"), ("design", "mobile_legibility"), ("design", "cover_strength"), ("design", "text_hierarchy"),
          ("caption", "caption_score")]
DISTS = [("script", "payoff", "reel"), ("script", "ending", "reel"), ("script", "cta_in_video", "reel"), ("script", "evidence", "reel"),
         ("delivery", "presence", "reel"), ("delivery", "eye_line", "reel"),
         ("filming", "shot", "reel"), ("filming", "angle", "reel"), ("filming", "face_size", "reel"), ("filming", "camera", "reel"),
         ("filming", "b_roll", "reel"), ("editing", "subtitles", "reel"), ("editing", "pace", "reel"), ("editing", "retention_devices", "reel"),
         ("design", "template", "all"), ("design", "text_language_order", "static"), ("design", "logo", "all"),
         ("caption", "first_line_type", "all"), ("caption", "language", "all"), ("caption", "repeats_post", "all")]


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(st.median(xs), 2) if xs else None


def main():
    user = sys.argv[1].lstrip("@").lower()
    A = root(user) / "analysis"
    D = {r["shortcode"]: r for r in json.loads((A / "dataset.json").read_text(encoding="utf-8"))}
    gf = A / "genuine.json"
    G = (json.loads(gf.read_text(encoding="utf-8")).get("posts") or {}) if gf.exists() else {}
    C = {}
    for f in (A / "craft").glob("*.json"):
        try:
            C[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print("unreadable", f.name, e)
    codes = [c for c in C if c in D]
    judged = [c for c in codes if not D[c]["too_recent"] and not D[c]["boosted"]]
    lift = lambda c: D[c]["perf_lift"]  # noqa: E731
    glift = lambda c: (G.get(c) or {}).get("genuine_lift")  # noqa: E731

    def val(c, part, k):
        p = C[c].get(part) or {}
        return p.get(k) if p.get("applies", True) else None

    pools = {"reel": [c for c in judged if D[c]["type"] == "reel"], "static": [c for c in judged if D[c]["type"] != "reel"], "all": judged}
    L = [f"# Craft facts ({len(C)} reviews; {len(judged)} in the comparisons)", "", "## Scores (1 to 5), on their own\n",
         "| score | posts | mean | distribution |", "|---|---|---|---|"]
    for part, k in SCORES:
        vals = [val(c, part, k) for c in codes]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if vals:
            L.append(f"| {part}.{k} | {len(vals)} | {round(st.mean(vals), 2)} | {dict(sorted(Counter(vals).items()))} |")
    cs = [C[c].get("craft_score") for c in codes if isinstance(C[c].get("craft_score"), (int, float))]
    if cs:
        L.append(f"| craft_score | {len(cs)} | {round(st.mean(cs), 2)} | {dict(sorted(Counter(cs).items()))} |")
    lenses = defaultdict(list)
    for c in codes:
        for name, v in (C[c].get("lenses") or {}).items():
            if isinstance(v, dict) and isinstance(v.get("score"), (int, float)):
                lenses[name].append(v["score"])
    for name, vals in lenses.items():
        L.append(f"| lens {name} | {len(vals)} | {round(st.mean(vals), 2)} | {dict(sorted(Counter(vals).items()))} |")

    L.append("\n## Scores against performance (Spearman)\n\n| score | pool | rho lift | rho genuine | n |\n|---|---|---|---|---|")
    for part, k in SCORES:
        for pool in ("reel", "static"):
            ps = pools[pool]
            xs = [val(c, part, k) for c in ps]
            if sum(isinstance(x, (int, float)) for x in xs) >= 6:
                r1, n = spearman(xs, [lift(c) for c in ps])
                r2, _ = spearman(xs, [glift(c) for c in ps])
                L.append(f"| {part}.{k} | {pool} | {r1} | {r2} | {n} |")
    for pool in ("reel", "static"):
        ps = pools[pool]
        r1, n = spearman([C[c].get("craft_score") for c in ps], [lift(c) for c in ps])
        r2, _ = spearman([C[c].get("craft_score") for c in ps], [glift(c) for c in ps])
        L.append(f"| craft_score | {pool} | {r1} | {r2} | {n} |")

    for part, k, pool in DISTS:
        ps = pools[pool]
        groups = defaultdict(list)
        for c in ps:
            v = val(c, part, k)
            for x in (v if isinstance(v, list) else [v]):
                if x is not None and x != "":
                    groups[str(x)].append(c)
        if not groups:
            continue
        L.append(f"\n### {part}.{k} ({pool})\n\n| value | n | median lift | median genuine lift | share above 1 |\n|---|---|---|---|---|")
        for x, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            L.append(f"| {x} | {len(g)} | {med([lift(c) for c in g])} | {med([glift(c) for c in g])} | {round(sum(1 for c in g if (lift(c) or 0) > 1) / len(g), 2)} |")

    colours = Counter(x.lower() for c in codes for x in (val(c, "design", "colors") or []))
    L.append("\n## Colours named across posts\n\n" + ", ".join(f"{k} {v}" for k, v in colours.most_common(25)))
    terms = Counter(t.strip() for c in codes for t in (((C[c].get("script") or {}).get("word_choice") or {}).get("foreign_terms") or []))
    if terms:
        L.append("\n## Foreign or borrowed terms in speech\n\n" + ", ".join(f"{k} {v}" for k, v in terms.most_common(40)))
    errors = [(c, e) for c in codes for e in C[c].get("errors") or []]
    L.append(f"\n## Errors the reviewers found ({len(errors)})\n")
    for kind, n in Counter(e.get("kind") for _, e in errors).most_common():
        L.append(f"- {kind}: {n}")
    for c, e in errors:
        L.append(f"  - {c} {D[c]['posted'][:10]} [{e.get('kind')}] {e.get('where')}: {e.get('what')} | fix: {e.get('fix')}")
    L.append("\n## Highest and lowest craft scores\n")
    ranked = sorted(codes, key=lambda c: -(C[c].get("craft_score") or 0))
    for c in ranked[:10] + ranked[-10:]:
        L.append(f"- {c} {D[c]['type']} {D[c]['posted'][:10]} craft {C[c].get('craft_score')} lift {lift(c)} | {(C[c].get('top_fixes') or [''])[0][:180]}")
    L.append("\n## Craft score against lift: where they disagree\n")
    both = [c for c in judged if isinstance(C[c].get("craft_score"), (int, float)) and lift(c)]
    for c in sorted(both, key=lambda c: -(lift(c) or 0))[:6]:
        if C[c]["craft_score"] <= 2:
            L.append(f"- performed despite weak craft: {c} {D[c]['posted'][:10]} craft {C[c]['craft_score']} lift {lift(c)}")
    for c in sorted(both, key=lambda c: (lift(c) or 0))[:6]:
        if C[c]["craft_score"] >= 4:
            L.append(f"- strong craft that did not perform: {c} {D[c]['posted'][:10]} craft {C[c]['craft_score']} lift {lift(c)}")
    (A / "craft_facts.md").write_text("\n".join(L), encoding="utf-8")
    print(f"craft_facts.md: {len(L)} lines from {len(C)} reviews")


if __name__ == "__main__":
    main()
