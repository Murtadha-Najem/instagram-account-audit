"""Refresh the GraphQL query ids when Instagram changes them (collect.py then says a query "did not answer as expected").

Opens any public profile headless in Edge with the same cookies, scrolls the posts grid and the reels tab, records the
query ids the page sends, and writes them to config.json. Cookie values are never printed.

usage: python capture_doc_ids.py [username to open, default instagram] [--cookies PATH]
"""
import argparse
import http.cookiejar
import json
import time
from datetime import date
from urllib.parse import parse_qs

from common import CONFIG, HERE, cookies_path

WANT = {"PolarisProfilePostsQuery": "posts_first", "PolarisProfilePostsTabContentQuery_connection": "posts_next",
        "PolarisProfileReelsTabContentQuery_connection": "reels_tab"}


def main():
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser()
    ap.add_argument("username", nargs="?", default="instagram")
    ap.add_argument("--cookies")
    args = ap.parse_args()
    jar = http.cookiejar.MozillaCookieJar(str(cookies_path(args.cookies)))
    jar.load(ignore_discard=True, ignore_expires=True)
    cookies = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path or "/", "secure": True,
                "httpOnly": c.name == "sessionid", "sameSite": "Lax"} for c in jar if "instagram.com" in c.domain]
    found = {}
    with sync_playwright() as p:
        browser = CONFIG["edge"]
        b = (p.chromium.launch(channel="msedge", headless=True) if "msedge" in browser.lower()
             else p.chromium.launch(executable_path=browser, headless=True))
        ctx = b.new_context(user_agent=CONFIG["user_agent"], viewport={"width": 1280, "height": 900}, locale="en-US")
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req):
            if "/graphql/query" in req.url and req.method == "POST":
                q = parse_qs(req.post_data or "")
                name = (q.get("fb_api_req_friendly_name") or [""])[0]
                if name in WANT:
                    found[WANT[name]] = (q.get("doc_id") or [""])[0]
        page.on("request", on_request)
        for path in ("", "reels/"):
            page.goto(f"https://www.instagram.com/{args.username}/{path}", wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            for _ in range(5):
                page.mouse.wheel(0, 3000)
                time.sleep(3)
        b.close()
    print("found:", found)
    if not found:
        print("nothing captured: the cookies may have expired, or the page layout changed (see SKILL.md)")
        return
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    cfg["doc_ids"].update(found)
    cfg["doc_ids"]["checked"] = date.today().isoformat()
    (HERE / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config.json updated")


if __name__ == "__main__":
    main()
