"""Merge every collected layer of an account into one dataset and compute the engagement facts the report rests on.

usage: python build_dataset.py <username>
reads audit/{links.json, posts_raw.jsonl, reels_raw.jsonl, comments/, likers/, faces/matches.json, partners.json, tagged.json,
      highlights/, delivery/, owner_metrics.json, analysis/taxonomy.json, analysis/coding/, analysis/craft/} and the
      pipeline bundles
writes audit/analysis/dataset.json and facts.md

Performance is judged against the post's neighbours: lift = the post's value / the median of the same metric over the
N posts of the same kind on each side (N from config). Reels on plays, photos and carousels on likes; with the owner's
export, also on reach, shares and saves. Posts younger than the too-recent threshold and boosted posts stay in the
dataset but are left out of every comparison.
"""
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from common import CACHE, CONFIG, account, jl, root

AN = CONFIG["analysis"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def rolling_lift(posts, key, out_key=None, window=None):
    window = window or AN["lift_window"]
    out_key = out_key or f"{key}_lift"
    vals = [p.get(key) for p in posts]
    for i, p in enumerate(posts):
        if vals[i] is None:
            p[out_key] = None
            continue
        nb = [v for j, v in enumerate(vals[max(0, i - window):i + window + 1], start=max(0, i - window)) if j != i and v]
        base = med(nb)
        p[out_key] = round(vals[i] / base, 3) if base else None


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    if len(pairs) < 6:
        return None, len(pairs)

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    a, b = rank([p[0] for p in pairs]), rank([p[1] for p in pairs])
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return (round(num / den, 3) if den else None), len(pairs)


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load(user):
    R = root(user)
    A = R / "analysis"
    acc = account(user)
    tz = timezone(timedelta(hours=acc.get("utc_offset_hours", 3)))
    links = json.loads((R / "links.json").read_text(encoding="utf-8"))
    raw = {x["code"]: x for x in jl(R / "posts_raw.jsonl")}
    reels_raw = {x["code"]: x for x in jl(R / "reels_raw.jsonl")}
    matches = load_json(R / "faces" / "matches.json", {})
    partners = {p["username"]: p for p in load_json(R / "partners.json", [])}
    owner = load_json(R / "owner_metrics.json", {})
    group = {g.lower() for g in acc["group_accounts"]}
    posts = []
    for l in links:
        code = l["shortcode"]
        x = raw.get(code) or reels_raw.get(code) or {}
        rr = reels_raw.get(code) or {}
        bundle = load_json(CACHE / code / "bundle.json", {})
        taken = x.get("taken_at")
        dt = datetime.fromtimestamp(taken, tz) if taken else None
        video = bundle.get("video") or {}
        speech = bundle.get("speech") if isinstance(bundle.get("speech"), dict) else {}
        m = matches.get(code, {})
        on_screen = {n: p for n, p in (m.get("people") or {}).items() if p["detections"] >= AN["presence_min_frames"]}
        coauthors = [c.get("username") for c in (x.get("coauthor_producers") or [])]
        own = (x.get("user") or {}).get("username")
        partner_names = [u for u in coauthors + ([own] if own and own != user else []) if u and u != user]
        caption = ((x.get("caption") or {}) or {}).get("text") or ""
        cm = load_json(R / "comments" / f"{code}.json", {}).get("comments") or []
        lk = load_json(R / "likers" / f"{code}.json", {}).get("likers") or []
        duration = bundle.get("duration") or x.get("video_duration")
        o = owner.get(code) or {}
        posts.append({
            "shortcode": code, "type": l["type"], "href": l["href"],
            "posted": dt.strftime("%Y-%m-%d %H:%M") if dt else None, "month": dt.strftime("%Y-%m") if dt else None,
            "hour": dt.hour if dt else None, "weekday": WEEKDAYS[dt.weekday()] if dt else None,
            "duration_s": round(duration, 1) if duration and l["type"] == "reel" else None,
            "slides": x.get("carousel_media_count"),
            "plays": rr.get("play_count") or x.get("play_count") or l.get("plays") or ((bundle.get("meta") or {}).get("views") if l["type"] == "reel" else None),
            "likes": x.get("like_count", l.get("likes")), "comments": x.get("comment_count", l.get("comments")),
            "reposts": x.get("media_repost_count"),
            "likes_hidden": bool(x.get("like_and_view_counts_disabled")), "paid_partnership": bool(x.get("is_paid_partnership")),
            "boosted": bool(o.get("boosted")),
            "reach": o.get("reach"), "views_owner": o.get("views"), "shares": o.get("shares"), "saves": o.get("saves"),
            "follows": o.get("follows"), "profile_visits": o.get("profile_visits"), "watch_time": o.get("watch_time"),
            "collab": bool(partner_names), "partners": partner_names,
            "partner_kind": ("external" if any(u.lower() not in group for u in partner_names) else "group") if partner_names else "solo",
            "partner_followers_max": max([partners.get(u, {}).get("followers") or 0 for u in partner_names], default=0),
            "owner": own, "in_grid": l.get("in_grid", True),
            "too_recent": (l.get("hours_old") or 10 ** 6) < AN["too_recent_hours"],
            "usertags": [((t.get("user") or {}).get("username")) for t in ((x.get("usertags") or {}).get("in") or [])],
            "location": (x.get("location") or {}).get("name"),
            "caption_len": len(caption), "hashtags": len(re.findall(r"#\w+", caption)), "caption": caption,
            "music": ((bundle.get("audio") or {}).get("song") or {}).get("title"), "audio_kind": (bundle.get("audio") or {}).get("kind"),
            "speech_source": speech.get("source"),
            "cuts": video.get("cuts"), "shots": video.get("shots"), "text_changes": video.get("text_changes"),
            "static_ratio": video.get("static_ratio"),
            "cuts_per_min": round(60 * video["cuts"] / duration, 1) if video.get("cuts") is not None and duration and l["type"] == "reel" else None,
            "people_on_screen": sorted(on_screen), "people_kinds": {n: p["kind"] for n, p in on_screen.items()},
            "faces_total": m.get("faces", 0),
            "delivery": load_json(R / "delivery" / f"{code}.json", None),
            "comments_list": cm, "likers_list": lk,
            "craft": load_json(A / "craft" / f"{code}.json", {}),
        })
        # content-only mode has no content pass: the craft reviewers wrote the basics instead
        posts[-1]["coding"] = load_json(A / "coding" / f"{code}.json", {}) or (posts[-1]["craft"].get("basics") or {})
    posts.sort(key=lambda p: p["posted"] or "")
    return posts, partners, acc


def group_table(posts, key_fn, min_n=2):
    groups = defaultdict(list)
    for p in posts:
        for k in (key_fn(p) or []):
            if k is not None and k != "":
                groups[str(k)].append(p)
    rows = []
    for k, ps in groups.items():
        if len(ps) < min_n:
            continue
        rows.append({"group": k, "n": len(ps), "median_plays": med([p["plays"] for p in ps]), "median_likes": med([p["likes"] for p in ps]),
                     "median_lift": med([p.get("perf_lift") for p in ps]),
                     "share_above": round(sum(1 for p in ps if (p.get("perf_lift") or 0) > 1) / len(ps), 2),
                     "examples": [p["shortcode"] for p in sorted(ps, key=lambda p: -(p.get("perf_lift") or 0))[:3]]})
    return sorted(rows, key=lambda r: -(r["median_lift"] or 0))


def fmt_table(rows, title):
    out = [f"### {title}", "", "| group | n | median plays | median likes | median lift | share above 1 | best examples |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['group']} | {r['n']} | {r['median_plays'] if r['median_plays'] is not None else '-'} | {r['median_likes']} | "
                   f"{r['median_lift']} | {r['share_above']} | {', '.join(r['examples'])} |")
    return "\n".join(out) + "\n"


def main():
    user = sys.argv[1].lstrip("@").lower()
    R = root(user)
    A = R / "analysis"
    A.mkdir(exist_ok=True)
    posts, partners, acc = load(user)
    judged = [p for p in posts if not p["too_recent"] and not p["boosted"]]
    reels = [p for p in judged if p["type"] == "reel"]
    static = [p for p in judged if p["type"] != "reel"]
    for p in posts:
        p["perf_lift"] = None
    rolling_lift(reels, "plays")
    rolling_lift(static, "likes")
    for p in reels:
        p["perf_lift"] = p.get("plays_lift")
    for p in static:
        p["perf_lift"] = p.get("likes_lift")
    has_owner = any(p["reach"] for p in posts)
    if has_owner:
        for grp in (reels, static):
            for k in ("reach", "shares", "saves", "follows"):
                rolling_lift(grp, k)
    for p in posts:
        p["like_rate"] = round(p["likes"] / p["plays"], 4) if p["plays"] and p["likes"] is not None else None
        p["comments_per_1k"] = round(1000 * (p["comments"] or 0) / p["plays"], 2) if p["plays"] else None
        if p["reach"]:
            p["share_rate"] = round((p["shares"] or 0) / p["reach"], 4)
            p["save_rate"] = round((p["saves"] or 0) / p["reach"], 4)

    c = lambda p: p["coding"]  # noqa: E731
    tax = load_json(A / "taxonomy.json", {})
    L = [f"# Engagement facts for @{user} (built {datetime.now().strftime('%Y-%m-%d %H:%M')})", ""]
    L.append(f"- Posts {len(posts)} ({dict(Counter(p['type'] for p in posts))}); judged {len(judged)}; too recent {sum(p['too_recent'] for p in posts)}; "
             f"boosted {sum(p['boosted'] for p in posts)}; coded {sum(1 for p in posts if c(p))}; craft-reviewed {sum(1 for p in posts if p['craft'])}")
    if posts:
        L.append(f"- Span {posts[0]['posted']} to {posts[-1]['posted']}; timezone UTC{acc.get('utc_offset_hours', 3):+d}")
    L.append(f"- Reel plays total {sum(p['plays'] or 0 for p in reels)}, median {med([p['plays'] for p in reels])}; likes total {sum(p['likes'] or 0 for p in judged)}; "
             f"comments {sum(p['comments'] or 0 for p in judged)}; reposts {sum(p['reposts'] or 0 for p in judged)}; hidden like counts {sum(p['likes_hidden'] for p in posts)}; "
             f"paid partnerships {sum(p['paid_partnership'] for p in posts)}")
    L.append(f"- Median like rate on reels {med([p['like_rate'] for p in reels])}; owner data present: {has_owner}")
    L.append(f"- Lift: the post's plays (reels) or likes (photos, carousels) / median of the {AN['lift_window']} posts of the same kind on each side; 1.0 = typical for its time.\n")

    L.append("## Month by month\n\n| month | posts | reels | carousels | photos | reel plays | likes | comments |\n|---|---|---|---|---|---|---|---|")
    for mth in sorted({p["month"] for p in judged if p["month"]}):
        ps = [p for p in judged if p["month"] == mth]
        L.append(f"| {mth} | {len(ps)} | {sum(p['type'] == 'reel' for p in ps)} | {sum(p['type'] == 'carousel' for p in ps)} | {sum(p['type'] == 'photo' for p in ps)} | "
                 f"{sum(p['plays'] or 0 for p in ps)} | {sum(p['likes'] or 0 for p in ps)} | {sum(p['comments'] or 0 for p in ps)} |")
    L.append("")
    L.append("## Top reels by plays\n\n| code | posted | plays | likes | comments | lift | partners | on screen | topic | format |\n|---|---|---|---|---|---|---|---|---|---|")
    for p in sorted(reels, key=lambda p: -(p["plays"] or 0))[:15]:
        L.append(f"| {p['shortcode']} | {p['posted']} | {p['plays']} | {p['likes']} | {p['comments']} | {p['perf_lift']} | {', '.join(p['partners']) or '-'} | "
                 f"{', '.join(p['people_on_screen']) or '-'} | {c(p).get('topic')} | {c(p).get('format')} |")
    L.append("\n## Highest and lowest lift\n\n| code | type | posted | lift | plays | likes | topic | format | hook |\n|---|---|---|---|---|---|---|---|---|")
    ranked = sorted([p for p in judged if p["perf_lift"]], key=lambda p: -p["perf_lift"])
    for p in ranked[:15] + [None] + ranked[-12:]:
        if p is None:
            L.append("| ... | | | | | | | | |")
            continue
        L.append(f"| {p['shortcode']} | {p['type']} | {p['posted']} | {p['perf_lift']} | {p['plays'] or '-'} | {p['likes']} | {c(p).get('topic')} | "
                 f"{c(p).get('format')} | {(c(p).get('hook') or {}).get('type')} |")
    L.append("")

    L.append("## What goes with higher performance (median lift by group, n >= 2)\n")
    band = lambda h: "00-08" if h < 9 else "09-14" if h < 15 else "15-18" if h < 19 else "19-23"  # noqa: E731
    length = lambda d: "<15s" if d < 15 else "15-30s" if d < 30 else "30-60s" if d < 60 else "60-90s" if d < 90 else "90s+"  # noqa: E731
    one = lambda k: (lambda p: [c(p).get(k)] if c(p) else [])  # noqa: E731
    specs = [("Post type", lambda p: [p["type"]]), ("Topic (main)", one("topic")), ("Topic (any)", lambda p: c(p).get("topics") or []),
             ("Format", one("format")), ("Presenter", one("presenter")),
             ("People on screen (faces)", lambda p: p["people_on_screen"] or ["nobody recognised"]),
             ("Hook type", lambda p: [(c(p).get("hook") or {}).get("type")] if c(p) else []),
             ("Hook strength", lambda p: [(c(p).get("hook") or {}).get("strength")] if c(p) else []),
             ("Structure", one("structure")), ("Spoken language", one("language")), ("On-screen text language", one("text_language")),
             ("Register", one("register")), ("Production", one("production")), ("Setting", one("setting")), ("Text density", one("text_density")),
             ("Subtitles", one("subtitles")), ("Music", one("music")), ("Call to action", lambda p: c(p).get("cta") or ["none"]),
             ("Value to viewer", one("value_to_viewer")), ("Audience", one("audience_target")), ("Tone", lambda p: c(p).get("tone") or []),
             ("Collab", lambda p: ["collab" if p["collab"] else "own"]), ("Partner kind", lambda p: [p["partner_kind"]]),
             ("Paid partnership", lambda p: ["paid" if p["paid_partnership"] else "not paid"]),
             ("Weekday", lambda p: [p["weekday"]]), ("Hour band", lambda p: [band(p["hour"])] if p["hour"] is not None else []),
             ("Reel length", lambda p: [length(p["duration_s"])] if p["duration_s"] else [])]
    for f in tax.get("custom_fields") or []:
        name = f["name"]
        specs.append((f"Custom: {name}", lambda p, name=name: (lambda v: v if isinstance(v, list) else [v])((c(p).get("custom") or {}).get(name))))
    for title, fn in specs:
        L.append(fmt_table(group_table(judged, fn), title))
        if title in ("Format", "Topic (main)", "Presenter", "Hook type", "People on screen (faces)"):
            L.append(fmt_table(group_table(reels, fn), title + ", reels only"))

    L.append("## Rank correlations with lift (Spearman)\n\n| variable | rho | n |\n|---|---|---|")
    for name, fn, ps in [("hook strength, reels", lambda p: (c(p).get("hook") or {}).get("strength"), reels),
                         ("seconds to the point, reels", lambda p: (c(p).get("hook") or {}).get("seconds_to_point"), reels),
                         ("clarity, reels", lambda p: c(p).get("clarity"), reels), ("energy, reels", lambda p: c(p).get("energy"), reels),
                         ("duration, reels", lambda p: p["duration_s"], reels), ("cuts per minute, reels", lambda p: p["cuts_per_min"], reels),
                         ("on-screen text changes, reels", lambda p: p["text_changes"], reels),
                         ("numbers cited, reels", lambda p: c(p).get("numbers_cited"), reels),
                         ("partner followers, collab reels", lambda p: p["partner_followers_max"] or None, reels),
                         ("hook strength, static", lambda p: (c(p).get("hook") or {}).get("strength"), static),
                         ("slides, carousels", lambda p: p["slides"], [p for p in static if p["type"] == "carousel"]),
                         ("caption length, all", lambda p: p["caption_len"], judged),
                         ("hashtags, all", lambda p: p["hashtags"], judged),
                         ("heard energy (Gemini), reels", lambda p: (p["delivery"] or {}).get("energy"), reels),
                         ("heard clarity (Gemini), reels", lambda p: (p["delivery"] or {}).get("clarity"), reels),
                         ("heard confidence (Gemini), reels", lambda p: (p["delivery"] or {}).get("confidence"), reels),
                         ("audio quality (Gemini), reels", lambda p: (p["delivery"] or {}).get("audio_quality"), reels)]:
        rho, n = spearman([fn(p) for p in ps], [p["perf_lift"] for p in ps])
        L.append(f"| {name} | {rho} | {n} |")
    L.append("")
    if has_owner:
        L.append("## Owner data (Meta export)\n")
        for k in ("reach", "shares", "saves", "follows"):
            L.append(f"- {k}: total {sum(p[k] or 0 for p in judged)}, median reels {med([p[k] for p in reels])}, median static {med([p[k] for p in static])}")
        L.append(f"- share rate median {med([p.get('share_rate') for p in judged])}; save rate median {med([p.get('save_rate') for p in judged])}")
        for title, fn in specs[:6]:
            rows = defaultdict(list)
            for p in judged:
                for k in fn(p) or []:
                    rows[str(k)].append(p)
            L.append(f"\n### {title} on reach, shares and saves lift\n\n| group | n | reach lift | shares lift | saves lift |\n|---|---|---|---|---|")
            for k, ps in sorted(rows.items(), key=lambda kv: -(med([p.get('reach_lift') for p in kv[1]]) or 0)):
                if len(ps) >= 2:
                    L.append(f"| {k} | {len(ps)} | {med([p.get('reach_lift') for p in ps])} | {med([p.get('shares_lift') for p in ps])} | {med([p.get('saves_lift') for p in ps])} |")
        L.append("")

    allc = [dict(cm, post=p["shortcode"]) for p in judged for cm in p["comments_list"]]
    if allc or any(p["comments"] for p in judged):
        cats = Counter(cc.get("category") for p in judged for cc in c(p).get("comments_coded") or [])
        pub = [cm for cm in allc if not cm["parent"] and not cm["is_account"]]
        replied = {cm["parent"] for cm in allc if cm["is_account"] and cm["parent"]}
        commenters = Counter(cm["author"] for cm in allc if not cm["is_account"])
        L.append("## Comments\n")
        L.append(f"- Collected {len(allc)} (counters say {sum(p['comments'] or 0 for p in judged)}); replies {sum(1 for cm in allc if cm['parent'])}; "
                 f"by the account {sum(cm['is_account'] for cm in allc)}; liked by the account {sum(1 for cm in allc if cm.get('liked_by_account'))}")
        L.append(f"- Public top-level comments {len(pub)}, answered by the account {len([cm for cm in pub if cm['id'] in replied])}")
        L.append(f"- Distinct commenters {len(commenters)}; with 3+ comments {sum(1 for v in commenters.values() if v >= 3)}; posts without comments {sum(1 for p in judged if not p['comments'])}")
        L.append(f"- Categories (coded): {dict(cats.most_common())}")
        L.append("- Most commented: " + "; ".join(f"{p['shortcode']} {p['comments']}" for p in sorted(judged, key=lambda p: -(p['comments'] or 0))[:8]))
        L.append("")

    likes_by, meta = Counter(), {}
    for p in judged:
        for u in p["likers_list"]:
            likes_by[u["username"]] += 1
            meta[u["username"]] = u
    if likes_by:
        tot = sum(likes_by.values())
        L.append("## Who likes (lists hold about 100 per post)\n")
        L.append(f"- Likes in lists {tot} over {sum(1 for p in judged if p['likers_list'])} posts; distinct accounts {len(likes_by)}")
        for k in (1, 2, 5, 10, 20):
            L.append(f"  - accounts that liked {k}+ posts: {sum(1 for v in likes_by.values() if v >= k)}")
        L.append(f"- Verified likers {sum(1 for u in likes_by if meta[u].get('is_verified'))}; private share {round(sum(1 for u in likes_by if meta[u].get('is_private')) / len(likes_by), 2)}")
        L.append("- See genuine_facts.md for the internal circle and genuine engagement.\n")

    if partners:
        L.append("## Partners, group accounts and accounts that tag this one\n\n| account | followers | roles | posts with them | median lift |\n|---|---|---|---|---|")
        for u, pr in sorted(partners.items(), key=lambda kv: -(kv[1].get("followers") or 0)):
            ps = [p for p in judged if u in p["partners"]]
            L.append(f"| {u} | {pr.get('followers')} | {', '.join(pr.get('roles') or [])} | {len(ps)} | {med([p['perf_lift'] for p in ps])} |")
        tagged = load_json(R / "tagged.json", [])
        L.append(f"\n- Tagged tab in the window: {len(tagged)} posts by {len({t['owner'] for t in tagged})} accounts: " +
                 ", ".join(f"{u} {n}" for u, n in Counter(t["owner"] for t in tagged).most_common(20)))
        L.append("")
    hl = load_json(R / "highlights" / "highlights_raw.json", [])
    if hl:
        L.append("## Highlights\n")
        for h in hl:
            links_ = sorted({l for s in h["stories"] for l in s["links"] if l})
            L.append(f"- {h['title']}: {h['items']} stories; links {links_[:3]}; mentions {sorted({m for s in h['stories'] for m in s['mentions'] if m})[:6]}")
        L.append("")
    dl = [p for p in judged if p["delivery"]]
    if dl:
        L.append("## Delivery as heard (Gemini), video posts with speech\n\n| code | posted | pace | energy | clarity | confidence | fillers | audio | music | lift |\n|---|---|---|---|---|---|---|---|---|---|")
        for p in dl:
            d = p["delivery"]
            L.append(f"| {p['shortcode']} | {p['posted'][:10]} | {d.get('pace')} | {d.get('energy')} | {d.get('clarity')} | {d.get('confidence')} | "
                     f"{d.get('fillers')} | {d.get('audio_quality')} | {d.get('music')} | {p['perf_lift']} |")
        L.append("")
    (A / "facts.md").write_text("\n".join(str(x) for x in L), encoding="utf-8")
    slim = [{k: v for k, v in p.items() if k not in ("comments_list", "likers_list")} for p in posts]
    (A / "dataset.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"facts.md {len(L)} lines; dataset.json {len(slim)} posts ({len(judged)} judged, {sum(1 for p in posts if c(p))} coded)")


if __name__ == "__main__":
    main()
