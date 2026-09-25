"""Shared paths, settings and the Instagram web session for the account-audit skill.

Every collection script uses the same logged-in cookies file (Netscape format). The reel pipeline's file is the
default; a spare login's file can be passed with --cookies so a large account never loads the user's main login.
Requests are paced by a profile from config.json ("normal" or "slow"); a refusal stops the run instead of retrying hard.
"""
import html
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
SKILL = HERE.parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
PROJECT = Path(CONFIG["project_root"])
CACHE = PROJECT / "data" / "cache"
NOT_PROFILES = {"p", "reel", "reels", "tv", "explore", "stories", "accounts", "direct"}
HEAVY = ("image_versions2", "video_versions", "preview", "display_uri", "media_cropping_info", "thumbnails",
         "video_dash_manifest")


class CollectError(Exception):
    """A failure with a message the user can act on."""


def username_from(arg):
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", arg)
    name = (m.group(1) if m else arg).strip().lstrip("@").strip("/").lower()
    if name in NOT_PROFILES or not re.fullmatch(r"[a-z0-9_.]{1,30}", name):
        raise CollectError(f"not a profile link or username: {arg}")
    return name


def root(user):
    """Everything this skill writes for one account lives here."""
    d = PROJECT / "profiles" / user / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def account(user):
    """account.json: what the user told us about the account. Every field is optional."""
    f = root(user) / "account.json"
    a = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    a.setdefault("username", user)
    a.setdefault("group_accounts", [])
    a.setdefault("team", [])
    a.setdefault("face_names", {})
    a.setdefault("pace", "normal")
    return a


def save_account(user, a):
    (root(user) / "account.json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")


def jl(path):
    path = Path(path)
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if path.exists() else []


def cookies_path(arg=None, user=None):
    if arg:
        return Path(arg).expanduser()
    if user:
        c = account(user).get("cookies")
        if c:
            return Path(c).expanduser()
    return Path(CONFIG["default_cookies"]).expanduser()


class Pacer:
    """Random pauses from the chosen profile, plus a long break every N requests on the slow profile."""

    def __init__(self, name="normal"):
        self.p = CONFIG["pace"][name]
        self.name = name
        self.count = 0

    def wait(self, kind="item"):
        self.count += 1
        time.sleep(random.uniform(*self.p[kind]))
        if self.p["break_every"] and self.count % self.p["break_every"] == 0:
            pause = random.uniform(*self.p["break"])
            print(f"  pause of {pause:.0f}s after {self.count} requests (slow pace)", flush=True)
            time.sleep(pause)


def session(cookies=None):
    path = cookies_path(cookies)
    if not path.exists():
        raise CollectError(f"cookies file missing: export Instagram cookies while logged in to {path}")
    jar = http.cookiejar.MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    values = {c.name: c.value for c in jar}
    if "sessionid" not in values:
        raise CollectError(f"{path} has no Instagram session: export it again while logged in")
    s = requests.Session()
    s.cookies = jar
    s.headers.update({"user-agent": CONFIG["user_agent"], "x-ig-app-id": CONFIG["app_id"],
                      "x-csrftoken": values.get("csrftoken", ""), "x-requested-with": "XMLHttpRequest", "accept": "*/*",
                      "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors"})
    s.viewer_id = values.get("ds_user_id")
    return s


def call(s, method, url, **kw):
    for attempt in range(5):
        try:
            r = s.request(method, url, timeout=40, allow_redirects=False, **kw)
        except requests.exceptions.ConnectionError:
            wait = 60 * (attempt + 1)
            print(f"  connection lost, retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code in (301, 302) and "login" in r.headers.get("location", ""):
            raise CollectError("Instagram wants a login: the cookies expired, export them again")
        if r.status_code == 429 or r.status_code >= 500:
            wait = 60 * (attempt + 1)
            print(f"  Instagram answered {r.status_code}, waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code in (401, 403):
            raise CollectError(f"Instagram refused the request ({r.status_code}): the cookies may have expired or the "
                               "login is restricted. Stop, and try later or with a spare login")
        return r
    raise CollectError("Instagram kept refusing (rate limit). Stop here and run again later; nothing collected is lost")


def get_json(s, url, referer):
    """GET an API url and return its JSON; an HTML page or an empty answer means Instagram is throttling or has logged
    the session out, and stops the run with a message instead of a traceback."""
    r = call(s, "GET", url, headers={"referer": referer})
    try:
        return r.json()
    except ValueError:
        raise CollectError(f"Instagram answered {r.status_code} without data on {url.split('?')[0]}: it is probably "
                           "throttling this login. Stop, wait a few hours (or use a spare login), then run again; "
                           "finished work is kept")


def gql(s, doc_key, name, variables, referer):
    r = call(s, "POST", "https://www.instagram.com/graphql/query",
             headers={"referer": referer, "content-type": "application/x-www-form-urlencoded"},
             data={"doc_id": CONFIG["doc_ids"][doc_key], "variables": json.dumps(variables), "fb_api_req_friendly_name": name})
    try:
        return r.json()["data"]
    except Exception:
        raise CollectError(f"{name} did not answer as expected, most likely because Instagram changed its query ids. "
                           f"Run capture_doc_ids.py. Response start: " + r.text[:200].replace("\n", " "))


def find_user(s, username):
    r = call(s, "GET", f"https://www.instagram.com/web/search/topsearch/?query={username}",
             headers={"referer": f"https://www.instagram.com/{username}/"})
    for entry in r.json().get("users", []):
        u = entry.get("user", {})
        if u.get("username", "").lower() == username:
            return {"username": u["username"], "user_id": str(u.get("pk") or u.get("pk_id")), "full_name": u.get("full_name"),
                    "is_verified": u.get("is_verified"), "is_private": u.get("is_private")}
    raise CollectError(f"no Instagram account named @{username} was found")


def count(txt):
    txt = txt.replace(",", "").strip()
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(txt[-1:].upper(), 1)
    return int(float(txt.rstrip("KkMmBb")) * mult)


def header(s, username):
    """Followers, following, posts, name and bio from the public profile page's meta description (the JSON profile
    endpoints answer 429 to a web session)."""
    r = call(s, "GET", f"https://www.instagram.com/{username}/",
             headers={"accept": "text/html", "x-requested-with": None, "sec-fetch-mode": "navigate", "sec-fetch-site": "none"})
    m = re.search(r'<meta content="([^"]+)" name="description"', r.text) or \
        re.search(r'<meta name="description" content="([^"]+)"', r.text)
    desc = html.unescape(m.group(1)) if m else ""
    nums = re.match(r"\s*([\d.,]+[KMB]?) Followers, ([\d.,]+[KMB]?) Following, ([\d.,]+[KMB]?) Posts - (.*?) \(@", desc)
    return {"username": username, "followers": count(nums.group(1)) if nums else None,
            "following": count(nums.group(2)) if nums else None, "posts": count(nums.group(3)) if nums else None,
            "name": nums.group(4).strip("‎ ") if nums else None,
            "bio": desc.split(': "', 1)[1].rstrip('"') if ': "' in desc else None,
            "checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}


def run_main(fn):
    try:
        fn()
    except CollectError as e:
        print(f"COLLECT ERROR: {e}", file=sys.stderr)
        sys.exit(1)
