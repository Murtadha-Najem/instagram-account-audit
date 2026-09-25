"""Collect everything public about one Instagram account, layer by layer. Every layer is resumable and paced.

usage: python collect.py <layer> <profile link or username> [--since YYYY-MM-DD] [--cookies PATH] [--pace normal|slow]
layers:
  posts       profile header, the posts grid and the reels tab (play counts): posts_raw.jsonl, reels_raw.jsonl,
              links.json (newest first, inside the window), profile.json
  comments    every comment and reply of every post: comments/<code>.json
  likers      who liked each post (Instagram shows about 100 per post): likers/<code>.json
  tagged      posts by other accounts that tag this one: tagged.json
  partners    follower counts of co-authors, collab owners, tagging accounts and the group's own accounts: partners.json
  highlights  story highlights, metadata and media: highlights/
  slides      downloads and transcribes every video slide of carousels with more than one video: data/cache/<code>/slides/
  all         every layer above, in that order
The window (--since) defaults to account.json "since", else 365 days back. Pinned posts older than it are dropped.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from common import (CACHE, HEAVY, PROJECT, CollectError, Pacer, account, call, cookies_path, find_user, get_json, gql, header, jl,
                    root, run_main, save_account, session, username_from)

KINDS = {1: "photo", 2: "video", 8: "carousel"}
PROVIDERS = {"__relay_internal__pv__PolarisMultiCaptionCarouselEnabledrelayprovider": True,
             "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": True,
             "__relay_internal__pv__PolarisReelsRecoDebugOverlayEnabledrelayprovider": False}
DATA = {"count": 12, "include_reel_media_seen_timestamp": True, "include_relationship_info": True,
        "latest_besties_reel_media": True, "latest_reel_media": True}


def slim(x):
    """Drop image and video URLs (they expire and weigh most of the file), recursively into carousel slides."""
    out = {k: v for k, v in x.items() if k not in HEAVY}
    if out.get("carousel_media"):
        out["carousel_media"] = [{k: v for k, v in m.items() if k not in HEAVY} for m in out["carousel_media"]]
    return out


def post_type(x):
    return "reel" if x.get("product_type") == "clips" else KINDS.get(x.get("media_type"), str(x.get("media_type")))


def grid_pages(s, username, pacer, after=None):
    """Yields (nodes, end_cursor) page by page from the posts grid."""
    while True:
        ref = f"https://www.instagram.com/{username}/"
        if after is None:
            d = gql(s, "posts_first", "PolarisProfilePostsQuery", {"data": DATA, "username": username, **PROVIDERS}, ref)
        else:
            d = gql(s, "posts_next", "PolarisProfilePostsTabContentQuery_connection",
                    {"after": after, "before": None, "data": DATA, "first": 12, "include_multi_captions": True, "last": None,
                     "username": username, **PROVIDERS}, ref)
        conn = d["xdt_api__v1__feed__user_timeline_graphql_connection"]
        info = conn.get("page_info") or {}
        nxt = info.get("end_cursor") if info.get("has_next_page") else None
        yield [e["node"] for e in conn.get("edges") or []], nxt
        if not nxt:
            return
        after = nxt
        pacer.wait("page")


def since_of(user, arg):
    if arg:
        return arg
    return account(user).get("since") or (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")


def ts(day):
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def posts(s, user, pacer, since):
    R = root(user)
    state_f = R / "state_posts.json"
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
    prof = find_user(s, user)
    if prof.get("is_private"):
        print("  the account is private: only posts this login can see will be collected", flush=True)
    head = header(s, user)
    (R / "profile.json").write_text(json.dumps({**prof, **head, "since": since}, ensure_ascii=False, indent=1), encoding="utf-8")
    limit = ts(since)
    raw_f = R / "posts_raw.jsonl"
    if not state.get("posts_done"):
        seen = {x["code"] for x in jl(raw_f)}
        for nodes, cursor in grid_pages(s, user, pacer, state.get("posts_cursor")):
            new = [n for n in nodes if n.get("code") not in seen]
            with raw_f.open("a", encoding="utf-8") as f:
                for n in new:
                    f.write(json.dumps(slim(n), ensure_ascii=False) + "\n")
                    seen.add(n["code"])
            state["posts_cursor"] = cursor
            state_f.write_text(json.dumps(state), encoding="utf-8")
            print(f"  posts: {len(seen)}", flush=True)
            if nodes and all((n.get("taken_at") or 0) < limit for n in nodes):
                break
        state["posts_done"] = True
        state_f.write_text(json.dumps(state), encoding="utf-8")
    reels_f = R / "reels_raw.jsonl"
    if not state.get("reels_done"):
        seen = {x["code"] for x in jl(reels_f)}
        grid_dates = {x["code"]: x.get("taken_at") for x in jl(raw_f)}
        after = state.get("reels_cursor")
        while True:
            v = {"data": {"include_feed_video": True, "page_size": 12, "target_user_id": prof["user_id"]}, "id": prof["user_id"],
                 "first": 12, "after": after, "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": True}
            d = gql(s, "reels_tab", "PolarisProfileReelsTabContentQuery_connection", v, f"https://www.instagram.com/{user}/reels/")
            conn = d["fetch__XDTUserDict"]["clips_connection"]
            nodes = [e["node"]["media"] for e in conn.get("edges") or []]
            # The reels tab carries play counts but no dates: take the date from the grid, or ask for the reels the grid
            # does not show (hidden from the grid, or posted from a partner's account).
            for n in nodes:
                n["taken_at"] = grid_dates.get(n.get("code"))
                if n["taken_at"] is None and n.get("code") not in seen:
                    pacer.wait("item")
                    info = get_json(s, f"https://www.instagram.com/api/v1/media/{n['pk']}/info/", f"https://www.instagram.com/{user}/reels/")
                    item = (info.get("items") or [{}])[0]
                    n["taken_at"] = item.get("taken_at")
                    n.setdefault("caption", item.get("caption"))
                    n.setdefault("usertags", item.get("usertags"))
                    n.setdefault("carousel_media_count", item.get("carousel_media_count"))
            with reels_f.open("a", encoding="utf-8") as f:
                for n in nodes:
                    if n.get("code") not in seen:
                        f.write(json.dumps(slim(n), ensure_ascii=False) + "\n")
                        seen.add(n["code"])
            info = conn.get("page_info") or {}
            after = info.get("end_cursor") if info.get("has_next_page") else None
            state["reels_cursor"] = after
            state_f.write_text(json.dumps(state), encoding="utf-8")
            print(f"  reels tab: {len(seen)}", flush=True)
            if not after or (nodes and all((n.get("taken_at") or 0) < limit for n in nodes)):
                break
            pacer.wait("page")
        state["reels_done"] = True
        state_f.write_text(json.dumps(state), encoding="utf-8")
    write_links(user, since)


def write_links(user, since):
    R = root(user)
    grid = {x["code"]: x for x in jl(R / "posts_raw.jsonl")}
    reels = {x["code"]: x for x in jl(R / "reels_raw.jsonl")}
    limit = ts(since)
    rows = [x for x in grid.values() if (x.get("taken_at") or 0) >= limit]
    # Reels that sit in the reels tab only (hidden from the grid, or owned by a partner) are posts of the account too.
    rows += [x for c, x in reels.items() if c not in grid and (x.get("taken_at") or 0) >= limit]
    rows.sort(key=lambda x: -(x.get("taken_at") or 0))
    now = time.time()
    links = []
    for x in rows:
        rr = reels.get(x["code"]) or {}
        links.append({"order": len(links) + 1, "shortcode": x["code"], "href": f"https://www.instagram.com/p/{x['code']}/",
                      "type": post_type(x), "taken_at": datetime.fromtimestamp(x["taken_at"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
                      "hours_old": round((now - x["taken_at"]) / 3600, 1),
                      "plays": rr.get("play_count") or x.get("play_count") or rr.get("view_count") or x.get("view_count"),
                      "likes": x.get("like_count"), "comments": x.get("comment_count"),
                      "owner": (x.get("user") or {}).get("username"),
                      "coauthors": [c.get("username") for c in x.get("coauthor_producers") or []],
                      "slides": x.get("carousel_media_count"), "in_grid": x["code"] in grid})
    (R / "links.json").write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"links.json: {len(links)} posts since {since}: {dict(Counter(l['type'] for l in links))}", flush=True)


def raw_posts(user):
    R = root(user)
    out = {}
    for name in ("posts_raw.jsonl", "reels_raw.jsonl"):
        for x in jl(R / name):
            out.setdefault(x["code"], x)
    keep = {l["shortcode"] for l in json.loads((R / "links.json").read_text(encoding="utf-8"))}
    return {c: x for c, x in out.items() if c in keep}


def comments(s, user, pacer, max_pages=0):
    R = root(user)
    out = R / "comments"
    out.mkdir(exist_ok=True)
    posts = raw_posts(user)

    def row(c, parent=None):
        author = (c.get("user") or {}).get("username")
        return {"id": str(c.get("pk")), "parent": parent, "author": author, "is_account": (author or "").lower() == user,
                "text": c.get("text"), "likes": c.get("comment_like_count"), "timestamp": c.get("created_at_utc") or c.get("created_at"),
                "liked_by_account": c.get("is_liked_by_media_owner")}

    def get(url, code):
        return get_json(s, url, f"https://www.instagram.com/p/{code}/")

    total = 0
    for n, (code, x) in enumerate(posts.items(), 1):
        f = out / f"{code}.json"
        if f.exists():
            continue
        cs, max_id, pages = [], None, 0
        while x.get("comment_count"):
            url = f"https://www.instagram.com/api/v1/media/{x['pk']}/comments/?can_support_threading=true&permalink_enabled=false"
            d = get(url + (f"&max_id={max_id}" if max_id else ""), code)
            pages += 1
            for c in d.get("comments") or []:
                cs.append(row(c))
                kids = c.get("preview_child_comments") or []
                if (c.get("child_comment_count") or 0) > len(kids):
                    pacer.wait("item")
                    kids = get(f"https://www.instagram.com/api/v1/media/{x['pk']}/comments/{c['pk']}/child_comments/", code).get("child_comments") or kids
                cs += [row(k, parent=str(c.get("pk"))) for k in kids]
            max_id = d.get("next_max_id")
            if not (d.get("has_more_comments") and max_id) or (max_pages and pages >= max_pages):
                break
            pacer.wait("page")
        f.write_text(json.dumps({"shortcode": code, "expected": x.get("comment_count"), "complete": not (max_pages and pages >= max_pages),
                                 "comments": cs}, ensure_ascii=False, indent=1), encoding="utf-8")
        total += len(cs)
        print(f"[{n}/{len(posts)}] {code}: {len(cs)} of {x.get('comment_count')}", flush=True)
        if x.get("comment_count"):
            pacer.wait("item")
    print("comments collected this run:", total)


def likers(s, user, pacer):
    out = root(user) / "likers"
    out.mkdir(exist_ok=True)
    posts = raw_posts(user)
    for n, (code, x) in enumerate(posts.items(), 1):
        f = out / f"{code}.json"
        if f.exists():
            continue
        if not x.get("like_count") and not x.get("like_and_view_counts_disabled"):
            f.write_text(json.dumps({"shortcode": code, "like_count": 0, "likers": []}), encoding="utf-8")
            continue
        d = get_json(s, f"https://www.instagram.com/api/v1/media/{x['pk']}/likers/", f"https://www.instagram.com/p/{code}/")
        users = [{"pk": str(u.get("pk")), "username": u.get("username"), "full_name": u.get("full_name"),
                  "is_verified": u.get("is_verified"), "is_private": u.get("is_private")} for u in d.get("users") or []]
        f.write_text(json.dumps({"shortcode": code, "like_count": x.get("like_count"), "user_count": d.get("user_count"),
                                 "likers": users}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{n}/{len(posts)}] {code}: {len(users)} likers of {x.get('like_count')}", flush=True)
        pacer.wait("item")


def tagged(s, user, pacer, since):
    R = root(user)
    uid = json.loads((R / "profile.json").read_text(encoding="utf-8"))["user_id"]
    items, max_id, page, limit = [], None, 0, ts(since)
    while True:
        url = f"https://www.instagram.com/api/v1/usertags/{uid}/feed/?count=12" + (f"&max_id={max_id}" if max_id else "")
        d = get_json(s, url, f"https://www.instagram.com/{user}/tagged/")
        page += 1
        batch = d.get("items") or []
        items += batch
        print(f"  tagged page {page}: {len(items)}", flush=True)
        max_id = d.get("next_max_id")
        if not d.get("more_available") or not max_id or (batch and all((x.get("taken_at") or 0) < limit for x in batch)):
            break
        pacer.wait("page")
    summary = [{"shortcode": x.get("code"), "href": f"https://www.instagram.com/p/{x.get('code')}/",
                "owner": (x.get("user") or {}).get("username"), "type": post_type(x),
                "taken_at": datetime.fromtimestamp(x["taken_at"], timezone.utc).strftime("%Y-%m-%d %H:%M") if x.get("taken_at") else None,
                "likes": x.get("like_count"), "comments": x.get("comment_count"), "plays": x.get("play_count"),
                "coauthors": [c.get("username") for c in x.get("coauthor_producers") or []],
                "caption": ((x.get("caption") or {}).get("text") or "")[:500]}
               for x in items if (x.get("taken_at") or 0) >= limit]
    (R / "tagged.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"tagged posts in the window: {len(summary)} from {len({t['owner'] for t in summary})} accounts")


def partners(s, user, pacer):
    R = root(user)
    names = {}
    for code, x in raw_posts(user).items():
        for c in x.get("coauthor_producers") or []:
            names.setdefault(c.get("username"), set()).add("coauthor")
        owner = (x.get("user") or {}).get("username")
        if owner and owner != user:
            names.setdefault(owner, set()).add("owner_of_collab")
    if (R / "tagged.json").exists():
        for t in json.loads((R / "tagged.json").read_text(encoding="utf-8")):
            names.setdefault(t["owner"], set()).add("tagged_account")
    for g in account(user)["group_accounts"]:
        names.setdefault(g, set()).add("group_account")
    names.pop(user, None)
    names.pop(None, None)
    f = R / "partners.json"
    done = {p["username"]: p for p in json.loads(f.read_text(encoding="utf-8"))} if f.exists() else {}
    for n, u in enumerate(sorted(names), 1):
        if u in done and done[u].get("followers") is not None:
            done[u]["roles"] = sorted(names[u])
            continue
        done[u] = {**header(s, u), "roles": sorted(names[u])}
        print(f"[{n}/{len(names)}] @{u}: {done[u]['followers']} followers ({', '.join(done[u]['roles'])})", flush=True)
        f.write_text(json.dumps(sorted(done.values(), key=lambda p: -(p["followers"] or 0)), ensure_ascii=False, indent=1), encoding="utf-8")
        pacer.wait("item")
    f.write_text(json.dumps(sorted(done.values(), key=lambda p: -(p["followers"] or 0)), ensure_ascii=False, indent=1), encoding="utf-8")


def best(cands):
    return max(cands, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))["url"] if cands else None


def highlights(s, user, pacer):
    R = root(user)
    out = R / "highlights"
    out.mkdir(exist_ok=True)
    uid = json.loads((R / "profile.json").read_text(encoding="utf-8"))["user_id"]
    tray = get_json(s, f"https://www.instagram.com/api/v1/highlights/{uid}/highlights_tray/", f"https://www.instagram.com/{user}/").get("tray") or []
    reels = {}
    for i in range(0, len(tray), 10):
        ids = [t["id"] for t in tray[i:i + 10]]
        pacer.wait("item")
        reels.update(get_json(s, "https://www.instagram.com/api/v1/feed/reels_media/?" + "&".join(f"reel_ids={x}" for x in ids),
                              f"https://www.instagram.com/{user}/").get("reels") or {})
    summary = []
    for n, t in enumerate(tray, 1):
        items = (reels.get(t["id"]) or {}).get("items") or []
        folder = out / f"{n:02d}_{re.sub(r'[^0-9A-Za-z؀-ۿ]+', '_', t.get('title') or 'untitled').strip('_') or 'pin'}"
        folder.mkdir(exist_ok=True)
        for k, it in enumerate(items, 1):
            video = best(it.get("video_versions") or [])
            url = video or best((it.get("image_versions2") or {}).get("candidates") or [])
            f = folder / f"{k:02d}.{'mp4' if video else 'jpg'}"
            if url and not f.exists():
                f.write_bytes(requests.get(url, timeout=90).content)
                time.sleep(0.5)
        summary.append({"id": t["id"], "title": t.get("title"), "folder": folder.name, "items": len(items),
                        "stories": [{"pk": it.get("pk"), "taken_at": it.get("taken_at"), "media_type": it.get("media_type"),
                                     "video_duration": it.get("video_duration"),
                                     "links": [(st.get("story_link") or {}).get("url") for st in it.get("story_link_stickers") or []],
                                     "mentions": [(m.get("user") or {}).get("username") for m in it.get("reel_mentions") or []],
                                     "feed_media": [(m.get("media_code") or m.get("media_id")) for m in it.get("story_feed_media") or []],
                                     "hashtags": [(h.get("hashtag") or {}).get("name") for h in it.get("story_hashtags") or []],
                                     "music": ((it.get("story_music_stickers") or [{}])[0].get("music_asset_info") or {}).get("title")}
                                    for it in items]})
        print(f"{t.get('title')}: {len(items)} stories", flush=True)
    (out / "highlights_raw.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


def slides(s, user, pacer):
    """The reel pipeline keeps a carousel's first video only; fetch and transcribe the others."""
    sys.path.insert(0, str(PROJECT))
    from reel.speech import transcribe
    for code, x in raw_posts(user).items():
        vids = [m for m in x.get("carousel_media") or [] if m.get("media_type") == 2]
        out = CACHE / code / "slides"
        if len(vids) < 2 or (out / "transcripts.json").exists():
            continue
        info = get_json(s, f"https://www.instagram.com/api/v1/media/{x['pk']}/info/", f"https://www.instagram.com/p/{code}/")["items"][0]
        out.mkdir(parents=True, exist_ok=True)
        results = []
        for n, m in enumerate(info.get("carousel_media") or [], 1):
            if m.get("media_type") != 2:
                continue
            f = out / f"slide_{n}.mp4"
            if not f.exists():
                f.write_bytes(requests.get(best(m.get("video_versions") or []), timeout=120).content)
                time.sleep(1)
            t = transcribe(f)
            results.append({"slide": n, "duration": m.get("video_duration"), "language": t["language"], "segments": t["segments"]})
        (out / "transcripts.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{code}: {len(results)} video slides transcribed", flush=True)
        pacer.wait("item")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layer", choices=["posts", "comments", "likers", "tagged", "partners", "highlights", "slides", "all"])
    ap.add_argument("profile")
    ap.add_argument("--since")
    ap.add_argument("--cookies")
    ap.add_argument("--pace", choices=["normal", "slow"])
    ap.add_argument("--max-comment-pages", type=int, default=0, help="0 = every page")
    args = ap.parse_args()
    user = username_from(args.profile)
    a = account(user)
    if args.cookies or args.pace:   # remembered for the pipeline and later layers
        a.update({k: v for k, v in (("cookies", args.cookies), ("pace", args.pace)) if v})
        save_account(user, a)
    s = session(str(cookies_path(args.cookies, user)))
    pacer = Pacer(args.pace or a.get("pace", "normal"))
    since = since_of(user, args.since)
    layers = ["posts", "comments", "likers", "tagged", "partners", "highlights", "slides"] if args.layer == "all" else [args.layer]
    for layer in layers:
        print(f"== {layer} (@{user}, since {since}, {pacer.name} pace)", flush=True)
        if layer == "posts":
            posts(s, user, pacer, since)
        elif layer == "comments":
            comments(s, user, pacer, args.max_comment_pages)
        elif layer == "likers":
            likers(s, user, pacer)
        elif layer == "tagged":
            tagged(s, user, pacer, since)
        elif layer == "partners":
            partners(s, user, pacer)
        elif layer == "highlights":
            highlights(s, user, pacer)
        elif layer == "slides":
            slides(s, user, pacer)


if __name__ == "__main__":
    run_main(main)
