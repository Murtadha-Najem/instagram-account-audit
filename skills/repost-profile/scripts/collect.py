"""Collect every repost of an Instagram account into its profile folder, straight from Instagram's web API.

Uses the same logged-in cookies as the reel pipeline. The username is resolved to an id through Instagram's search,
then the reposts grid query is paged until Instagram says there is no more. Pages are paced, and a refusal stops the
run instead of hammering the account.

usage: python collect.py <profile url or username> [--limit N]
writes <project>/profiles/<username>/profile.json, links.json (newest repost first) and grid_raw.jsonl
"""
import argparse
import http.cookiejar
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
PROJECT = Path(CONFIG["project_root"])
COOKIES = Path.home() / ".config" / "reel" / "cookies.txt"
NOT_PROFILES = {"p", "reel", "reels", "tv", "explore", "stories", "accounts", "direct"}
HEAVY_KEYS = ("image_versions2", "thumbnails", "preview", "display_uri", "media_cropping_info", "carousel_media")


class CollectError(Exception):
    """A failure with a message the user can act on."""


def username_from(arg):
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", arg)
    name = (m.group(1) if m else arg).strip().lstrip("@").strip("/").lower()
    if name in NOT_PROFILES or not re.fullmatch(r"[a-z0-9_.]{1,30}", name):
        raise CollectError(f"not a profile link or username: {arg}")
    return name


def session():
    if not COOKIES.exists():
        raise CollectError(f"cookies file missing: export Instagram cookies while logged in to {COOKIES}")
    jar = http.cookiejar.MozillaCookieJar(str(COOKIES))
    jar.load(ignore_discard=True, ignore_expires=True)
    values = {c.name: c.value for c in jar}
    if "sessionid" not in values:
        raise CollectError("the cookies file has no Instagram session: export it again while logged in")
    s = requests.Session()
    s.cookies = jar
    s.headers.update({
        "user-agent": CONFIG["user_agent"], "x-ig-app-id": CONFIG["app_id"], "x-csrftoken": values.get("csrftoken", ""),
        "x-requested-with": "XMLHttpRequest", "accept": "*/*", "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors",
    })
    return s, values.get("ds_user_id")


def call(s, method, url, **kw):
    for attempt in range(4):
        r = s.request(method, url, timeout=30, allow_redirects=False, **kw)
        if r.status_code in (301, 302) and "login" in r.headers.get("location", ""):
            raise CollectError("Instagram wants a login: the cookies expired, export them again")
        if r.status_code == 429 or r.status_code >= 500:
            wait = 45 * (attempt + 1)
            print(f"  Instagram answered {r.status_code}, waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code in (401, 403):
            raise CollectError(f"Instagram refused the request ({r.status_code}): the cookies may have expired")
        return r
    raise CollectError("Instagram kept refusing (rate limit). Stop here and run again later; nothing collected is lost")


def find_user(s, username):
    r = call(s, "GET", f"https://www.instagram.com/web/search/topsearch/?query={username}",
             headers={"referer": f"https://www.instagram.com/{username}/"})
    for entry in r.json().get("users", []):
        u = entry.get("user", {})
        if u.get("username", "").lower() == username:
            return {"username": u["username"], "user_id": str(u.get("pk") or u.get("pk_id")),
                    "full_name": u.get("full_name"), "is_verified": u.get("is_verified"),
                    "is_private": u.get("is_private")}
    raise CollectError(f"no Instagram account named @{username} was found")


def reposts_page(s, user, max_id):
    variables = {"id": user["user_id"], "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": False}
    if max_id:
        variables["max_id"] = max_id
    r = call(s, "POST", "https://www.instagram.com/graphql/query",
             headers={"referer": f"https://www.instagram.com/{user['username']}/reposts/",
                      "content-type": "application/x-www-form-urlencoded"},
             data={"doc_id": CONFIG["reposts_doc_id"], "variables": json.dumps(variables),
                   "fb_api_req_friendly_name": "PolarisProfileRepostsTabContentRefetchQuery"})
    try:
        return r.json()["data"]["fetch__XDTUserDict"]["user_reposts_timeline"]
    except Exception:
        raise CollectError("the reposts query did not answer as expected, most likely because Instagram changed its "
                           "query id. Refresh reposts_doc_id (SKILL.md, 'Refreshing the query id'). Response start: "
                           + r.text[:200].replace("\n", " "))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--limit", type=int, default=0, help="stop after N reposts (pilot runs)")
    args = ap.parse_args()

    username = username_from(args.profile)
    s, viewer_id = session()
    user = find_user(s, username)
    out = PROJECT / "profiles" / user["username"].lower()
    out.mkdir(parents=True, exist_ok=True)
    print(f"@{user['username']} id {user['user_id']} private={user['is_private']} -> {out}", flush=True)

    links, seen, raw_lines, max_id, pages = [], set(), [], None, 0
    while True:
        tl = reposts_page(s, user, max_id)
        pages += 1
        for item in tl.get("repost_grid_items") or []:
            media = item.get("media") or {}
            code = media.get("code")
            if not code or code in seen:
                continue
            seen.add(code)
            note = next((n for n in (media.get("media_notes") or {}).get("items") or []
                         if str(n.get("user_id")) == user["user_id"]), {})
            links.append({"order": len(links) + 1, "shortcode": code, "href": f"https://www.instagram.com/p/{code}/",
                          "owner": (media.get("user") or {}).get("username"), "note_text": note.get("text") or "",
                          "note_id": note.get("id")})
            raw_lines.append(json.dumps({k: v for k, v in media.items() if k not in HEAVY_KEYS}, ensure_ascii=False))
            if args.limit and len(links) >= args.limit:
                break
        print(f"  page {pages}: {len(links)} reposts so far", flush=True)
        if (args.limit and len(links) >= args.limit) or not tl.get("repost_more_available") or not tl.get("repost_next_max_id"):
            break
        max_id = tl["repost_next_max_id"]
        time.sleep(random.uniform(*CONFIG["page_pause_seconds"]))

    if not links:
        raise CollectError(f"@{user['username']} shows no reposts to this login (none made, reposts hidden, or a private account you do not follow)")
    profile = {**user, "viewer_id": viewer_id, "viewer_is_target": str(viewer_id) == user["user_id"],
               "collected_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "reposts": len(links),
               "pages": pages, "complete": not args.limit}
    (out / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "links.json").write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "grid_raw.jsonl").write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    print(json.dumps(profile, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except CollectError as e:
        print(f"COLLECT ERROR: {e}", file=sys.stderr)
        sys.exit(1)
