"""Separate the internal circle (team, friends, the account's own group) from genuine engagement.

A liker is judged over their own active window, from the first post they liked to the last: among the posts whose
liker list is complete enough to see them, what share did they like? Someone who liked more than half of everything
published while active, over a long enough window, likes the page rather than the content. The account itself, its
group accounts and the handles the user named as team always count as internal. Everyone else is genuine.

usage: python genuine.py <username>
writes audit/analysis/genuine.json and genuine_facts.md; skipped with a note when the lists are too partial to judge
(very large accounts, where Instagram shows only a small slice of each post's likers).
"""
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime

from common import CONFIG, account, root

H = CONFIG["analysis"]["habitual"]
WINDOW = CONFIG["analysis"]["lift_window"]


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def main():
    user = sys.argv[1].lstrip("@").lower()
    R = root(user)
    A = R / "analysis"
    acc = account(user)
    own = {user} | {g.lower() for g in acc["group_accounts"]}
    team = {h.lower(): p["name"] for p in acc["team"] for h in p.get("handles") or []}
    rows = [r for r in json.loads((A / "dataset.json").read_text(encoding="utf-8")) if r["posted"] and not r["too_recent"] and not r["boosted"]]
    rows.sort(key=lambda r: r["posted"])
    idx = {r["shortcode"]: i for i, r in enumerate(rows)}
    likers, complete = {}, {}
    for r in rows:
        f = R / "likers" / f"{r['shortcode']}.json"
        L = json.loads(f.read_text(encoding="utf-8"))["likers"] if f.exists() else []
        likers[r["shortcode"]] = L
        complete[r["shortcode"]] = bool(r["likes"]) and len(L) >= H["complete_list"] * r["likes"]
    n_complete = sum(complete.values())
    if n_complete < max(6, 0.2 * len(rows)):
        note = (f"# Genuine engagement\n\n- Skipped: only {n_complete} of {len(rows)} posts have a liker list complete enough to judge "
                f"(Instagram shows about 100 likers per post). On an account this size the internal circle cannot be measured; "
                f"the report says so and uses all likes.\n")
        (A / "genuine_facts.md").write_text(note, encoding="utf-8")
        (A / "genuine.json").write_text(json.dumps({"skipped": True, "complete_posts": n_complete}), encoding="utf-8")
        print(note)
        return
    liked, meta = defaultdict(list), {}
    for code, L in likers.items():
        for u in L:
            liked[u["username"]].append(idx[code])
            meta[u["username"]] = u
    people = {}
    for u, ids in liked.items():
        ids.sort()
        first, last = ids[0], ids[-1]
        window = [i for i in range(first, last + 1) if complete[rows[i]["shortcode"]]]
        seen = [i for i in ids if complete[rows[i]["shortcode"]]]
        share = len(seen) / len(window) if window else None
        days = (datetime.strptime(rows[last]["posted"][:10], "%Y-%m-%d") - datetime.strptime(rows[first]["posted"][:10], "%Y-%m-%d")).days
        habitual = len(window) >= H["min_window_posts"] and days >= H["min_days"] and share is not None and share > H["share"]
        people[u] = {"username": u, "full_name": meta[u].get("full_name"), "likes": len(ids),
                     "first": rows[first]["posted"][:10], "last": rows[last]["posted"][:10], "window_posts": len(window),
                     "window_days": days, "share_in_window": round(share, 2) if share is not None else None,
                     "team": team.get(u.lower()), "own_account": u.lower() in own,
                     "class": "habitual" if habitual else ("repeat" if len(ids) > 1 else "once")}
        people[u]["internal"] = habitual or people[u]["team"] is not None or people[u]["own_account"]
    internal = {u for u, p in people.items() if p["internal"]}
    per_post = {}
    for r in rows:
        L = likers[r["shortcode"]]
        h = sum(1 for u in L if u["username"] in internal)
        g = max(0, (r["likes"] or 0) - h)
        per_post[r["shortcode"]] = {"likes": r["likes"], "listed": len(L), "complete": complete[r["shortcode"]], "internal_likes": h,
                                    "genuine_likes": g, "internal_share": round(h / r["likes"], 3) if r["likes"] else None}
    for is_reel in (True, False):
        ps = [r for r in rows if (r["type"] == "reel") == is_reel]
        vals = [per_post[r["shortcode"]]["genuine_likes"] for r in ps]
        for i, r in enumerate(ps):
            nb = [v for j, v in enumerate(vals[max(0, i - WINDOW):i + WINDOW + 1], start=max(0, i - WINDOW)) if j != i and v]
            base = med(nb)
            per_post[r["shortcode"]]["genuine_lift"] = round(vals[i] / base, 3) if base else None
    (A / "genuine.json").write_text(json.dumps({"people": people, "posts": per_post, "rule": H}, ensure_ascii=False, indent=1), encoding="utf-8")

    tot = sum(p["likes"] for p in people.values())
    il = sum(people[u]["likes"] for u in internal)
    out = ["# Genuine engagement facts", "",
           f"- Rule: internal = the account and its group accounts, handles named as team, and anyone who liked more than "
           f"{int(H['share'] * 100)}% of the complete-list posts in their own active window (at least {H['min_window_posts']} posts over {H['min_days']} days).",
           f"- Likers {len(people)}; likes in lists {tot}; posts with a complete list {n_complete} of {len(rows)}",
           f"- Internal circle {len(internal)} accounts: {sum(1 for u in internal if people[u]['own_account'])} own/group accounts, "
           f"{sum(1 for u in internal if people[u]['team'])} team handles, {sum(1 for u in internal if not people[u]['own_account'] and not people[u]['team'])} "
           f"habitual others; their likes {il} = {round(il / max(1, tot), 3)} of listed likes",
           f"- Repeat but selective {sum(1 for p in people.values() if p['class'] == 'repeat' and not p['internal'])} accounts giving "
           f"{sum(p['likes'] for p in people.values() if p['class'] == 'repeat' and not p['internal'])} likes; once only {sum(1 for p in people.values() if p['class'] == 'once')}",
           "- Team handles found: " + "; ".join(f"{p['username']} ({p['team']}, {p['likes']} likes, share {p['share_in_window']})" for p in people.values() if p["team"]),
           "- Habitual accounts not named as team (count them, do not name them in the report): " +
           str(sum(1 for u in internal if not people[u]["own_account"] and not people[u]["team"])),
           f"- Median internal share of likes on complete posts: reels {med([per_post[r['shortcode']]['internal_share'] for r in rows if complete[r['shortcode']] and r['type'] == 'reel'])}, "
           f"static {med([per_post[r['shortcode']]['internal_share'] for r in rows if complete[r['shortcode']] and r['type'] != 'reel'])}",
           "\n## Posts by genuine likes\n\n| code | type | posted | likes | internal | genuine | internal share | genuine lift | lift |\n|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -per_post[r["shortcode"]]["genuine_likes"]):
        pp = per_post[r["shortcode"]]
        out.append(f"| {r['shortcode']} | {r['type']} | {r['posted'][:10]} | {r['likes']} | {pp['internal_likes']} | {pp['genuine_likes']} | "
                   f"{pp['internal_share']} | {pp.get('genuine_lift')} | {r['perf_lift']} |")
    cm_total = cm_int = 0
    for r in rows:
        f = R / "comments" / f"{r['shortcode']}.json"
        for c in (json.loads(f.read_text(encoding="utf-8"))["comments"] if f.exists() else []):
            if not c["is_account"]:
                cm_total += 1
                cm_int += c["author"] in internal
    out.append(f"\n- Public comments {cm_total}, from the internal circle {cm_int} ({round(cm_int / max(1, cm_total), 2)})")
    (A / "genuine_facts.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:9]))


if __name__ == "__main__":
    main()
