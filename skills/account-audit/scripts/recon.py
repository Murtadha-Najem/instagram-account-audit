"""A quick first look at an account, before anything is approved: header, the latest posts, a contact sheet of their
covers, and what each mode would cost for this account's size.

usage: python recon.py <profile link or username> [--since YYYY-MM-DD] [--cookies PATH] [--pages 2]
writes audit/recon/recon.json, recon.md (captions and numbers of the sample) and sheet.jpg (numbered covers)
Two grid pages (24 posts) and one profile page: a handful of requests.
"""
import argparse
import json
import math
import statistics as st
from collections import Counter
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import requests

from collect import grid_pages, post_type
from common import CONFIG, Pacer, account, cookies_path, find_user, header, root, run_main, session, username_from

COST = CONFIG["cost_per_post"]
SIZE = CONFIG["size_classes"]


def thumb(x):
    cands = (x.get("image_versions2") or {}).get("candidates") or []
    if not cands and x.get("carousel_media"):
        cands = (x["carousel_media"][0].get("image_versions2") or {}).get("candidates") or []
    ok = [c for c in cands if (c.get("width") or 0) >= 240]
    return min(ok, key=lambda c: c["width"])["url"] if ok else (cands[0]["url"] if cands else None)


def sheet(nodes, path):
    tiles = []
    for i, x in enumerate(nodes, 1):
        img = None
        url = thumb(x)
        if url:
            try:
                img = cv2.imdecode(np.frombuffer(requests.get(url, timeout=30).content, np.uint8), cv2.IMREAD_COLOR)
            except Exception:
                img = None
        if img is None:
            img = np.full((200, 200, 3), 230, np.uint8)
        h, w = img.shape[:2]
        side = min(h, w)
        img = cv2.resize(img[(h - side) // 2:(h + side) // 2, (w - side) // 2:(w + side) // 2], (200, 200))
        cv2.rectangle(img, (0, 0), (74, 26), (255, 255, 255), -1)
        cv2.putText(img, f"{i} {post_type(x)[0].upper()}", (4, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        tiles.append(img)
    while len(tiles) % 6:
        tiles.append(np.full((200, 200, 3), 255, np.uint8))
    rows = [np.concatenate(tiles[i:i + 6], 1) for i in range(0, len(tiles), 6)]
    cv2.imwrite(str(path), np.concatenate(rows, 0), [cv2.IMWRITE_JPEG_QUALITY, 80])


def fmt_time(sec):
    h = sec / 3600
    return f"{sec / 60:.0f} min" if h < 1 else f"{h:.1f} h"


def estimate(n, mix, avg_comments, pace, craft_n=None, content_n=None):
    """Tokens and wall-clock for one mode. n: posts in the window; mix: share of reel/carousel/photo."""
    counts = {k: n * mix.get(k, 0) for k in ("reel", "carousel", "photo")}
    slow = COST["slow_factor"] if pace == "slow" else 1.0
    c = COST["collect_seconds_normal"]

    def scaled(m):
        return {k: v * (m / n if n else 0) for k, v in counts.items()}
    content_counts = scaled(content_n if content_n is not None else n)
    craft_counts = scaled(craft_n if craft_n is not None else n)
    tok_content = sum(COST["content_tokens"][k] * v for k, v in content_counts.items())
    tok_craft = sum(COST["craft_tokens"][k] * v for k, v in craft_counts.items())
    t = {
        "collect_posts": (n / 12 * 2) * c["grid_page"] * slow,
        "collect_comments": n * (1 + avg_comments / 15) * c["comments_post"] * slow,
        "collect_likers": n * c["likers_post"] * slow,
        "collect_other": (15 + 0.3 * n / 4) * c["partner"] * slow + 60,
        "pipeline": sum(COST["pipeline_seconds"][k] * v for k, v in counts.items()) + (n * 10 if pace == "slow" else 0),
    }
    units_content = sum({"reel": 3, "carousel": 1.5, "photo": 1}[k] * v for k, v in content_counts.items())
    units_craft = sum({"reel": 3, "carousel": 2, "photo": 1}[k] * v for k, v in craft_counts.items())
    t["wave_content"] = 60 * units_content / max(1, min(10, math.ceil(units_content / 35))) if units_content else 0
    t["wave_craft"] = 90 * units_craft / max(1, min(10, math.ceil(units_craft / 35))) if units_craft else 0
    return tok_content, tok_craft, t


def modes(n, mix, avg_comments, pace):
    F = COST["fixed_tokens"]
    out = {}
    sample = min(25, n)
    for name in ("full", "engagement", "content", "brief"):
        if name == "full":
            tc, tk, t = estimate(n, mix, avg_comments, pace)
            tokens = tc + tk + F["profiler"] + F["panel"] + F["writers"] + F["orchestration"]
            wall = sum(t.values()) - t["collect_comments"] - t["collect_likers"] + 2700   # likers and comments overlap the pipeline
        elif name == "engagement":
            tc, tk, t = estimate(n, mix, avg_comments, pace, craft_n=0)
            tokens = tc + F["profiler"] + 0.5 * F["writers"] + 0.7 * F["orchestration"]
            wall = sum(t.values()) - t["collect_comments"] - t["collect_likers"] + 1800
        elif name == "content":
            tc, tk, t = estimate(n, mix, 0, pace, content_n=0)
            tk *= 1.12   # the craft pass also writes the basics the content pass would have
            tokens = tk + F["profiler"] + F["panel"] + 0.6 * F["writers"] + 0.7 * F["orchestration"]
            wall = t["collect_posts"] + t["pipeline"] + t["wave_craft"] + 2400
        else:
            tc, tk, t = estimate(n, mix, avg_comments, pace, craft_n=sample)
            tokens = tc + tk + F["profiler"] + 0.5 * F["panel"] + 0.4 * F["writers"] + 0.5 * F["orchestration"]
            wall = sum(t.values()) - t["collect_comments"] - t["collect_likers"] + 1500
        out[name] = {"tokens": int(round(tokens, -4)), "wall": fmt_time(wall), "wall_s": int(wall),
                     "collect": fmt_time(sum(v for k, v in t.items() if k.startswith("collect")))}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--since")
    ap.add_argument("--cookies")
    ap.add_argument("--pages", type=int, default=2)
    args = ap.parse_args()
    user = username_from(args.profile)
    out = root(user) / "recon"
    out.mkdir(exist_ok=True)
    s = session(str(cookies_path(args.cookies, user)))
    prof = find_user(s, user)
    head = header(s, user)
    nodes = []
    for page, (batch, _) in enumerate(grid_pages(s, user, Pacer("normal")), 1):
        nodes += batch
        if page >= args.pages:
            break
    since = args.since or account(user).get("since") or (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    limit = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    unpinned = [x for x in nodes if not x.get("timeline_pinned_user_ids")]
    dated = sorted(x["taken_at"] for x in unpinned if x.get("taken_at"))
    in_window = [x for x in unpinned if (x.get("taken_at") or 0) >= limit]
    if dated and dated[0] < limit:
        est, how = len(in_window), "exact (the sample reaches past the window start)"
    else:
        span = max(1.0, (dated[-1] - dated[0]) / 86400) if len(dated) > 1 else 30.0
        days = (datetime.now(timezone.utc).timestamp() - limit) / 86400
        est = int(min(head.get("posts") or 10 ** 6, len(dated) / span * days))
        how = f"extrapolated from {len(dated)} posts over {span:.0f} days"
    kinds = Counter(post_type(x) for x in unpinned)
    total = sum(kinds.values()) or 1
    mix = {k: kinds.get(k, 0) / total for k in ("reel", "carousel", "photo")}
    mix["reel"] += kinds.get("video", 0) / total
    med = lambda xs: st.median(xs) if xs else 0  # noqa: E731
    avg_comments = st.mean([x.get("comment_count") or 0 for x in unpinned]) if unpinned else 0
    followers = head.get("followers") or 0
    size = ("huge" if followers >= SIZE["huge_followers"] else
            "large" if followers >= SIZE["large_followers"] or est >= SIZE["large_posts"] else "normal")
    pace = "slow" if size != "normal" else "normal"
    result = {"username": user, "profile": {**prof, **head}, "since": since, "posts_in_window": est, "estimate_basis": how,
              "type_mix": {k: round(v, 2) for k, v in mix.items()}, "sample": len(nodes),
              "median_likes": med([x.get("like_count") or 0 for x in unpinned]),
              "mean_comments": round(avg_comments, 1),
              "hidden_like_counts": sum(1 for x in unpinned if x.get("like_and_view_counts_disabled")),
              "paid_partnerships": sum(1 for x in unpinned if x.get("is_paid_partnership")),
              "collabs": sum(1 for x in unpinned if x.get("coauthor_producers")),
              "size_class": size, "suggested_pace": pace, "modes": modes(est, mix, avg_comments, pace)}
    if est > 300:
        result["modes_sampled_150"] = modes(150, mix, avg_comments, pace)
    (out / "recon.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet(nodes, out / "sheet.jpg")
    L = [f"# Recon @{user}", "", f"- name: {head.get('name')}; bio: {head.get('bio')}",
         f"- followers {head.get('followers')}, following {head.get('following')}, posts {head.get('posts')}, "
         f"verified {prof.get('is_verified')}, private {prof.get('is_private')}", "",
         "| # | code | type | date | likes | plays | comments | collab | caption |", "|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(nodes, 1):
        cap = ((x.get("caption") or {}).get("text") or "").replace("\n", " ").replace("|", "/")[:220]
        L.append(f"| {i} | {x.get('code')} | {post_type(x)}{' pinned' if x.get('timeline_pinned_user_ids') else ''} | "
                 f"{datetime.fromtimestamp(x['taken_at'], timezone.utc).strftime('%Y-%m-%d') if x.get('taken_at') else ''} | "
                 f"{x.get('like_count')} | {x.get('play_count') or x.get('view_count') or ''} | {x.get('comment_count')} | "
                 f"{', '.join(c.get('username') for c in x.get('coauthor_producers') or [])} | {cap} |")
    (out / "recon.md").write_text("\n".join(L), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "profile"}, ensure_ascii=False, indent=1))
    print(f"sheet: {out / 'sheet.jpg'}\nsample: {out / 'recon.md'}")


if __name__ == "__main__":
    run_main(main)
