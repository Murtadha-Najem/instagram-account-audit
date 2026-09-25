"""Run the reel pipeline (batch.py, unchanged) over an account's posts, with this account's login and pace.

The pipeline reads a fixed cookies file and a fixed pause between downloads. For a spare login or the slow pace they
are swapped in memory for this run only; nothing in the reel skill is edited.

usage: python run_pipeline.py <username> [--workers 3] [--codes FILE]   (FILE: one shortcode per line, a subset)
results: <project>/batch/audit_<username>/results.jsonl, resumable
"""
import argparse
import json
import os
import sys
from pathlib import Path

from common import CACHE, CONFIG, PROJECT, account, cookies_path, root, username_from

sys.path.insert(0, str(PROJECT))
import batch  # noqa: E402

_init = batch.init_worker


def init_worker(*a):
    _init(*a)
    if os.environ.get("AUDIT_COOKIES"):
        from reel import common, download
        common.COOKIES = download.COOKIES = Path(os.environ["AUDIT_COOKIES"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--codes")
    args = ap.parse_args()
    user = username_from(args.profile)
    R = root(user)
    a = account(user)
    links = json.loads((R / "links.json").read_text(encoding="utf-8"))
    if args.codes:
        keep = {l.strip() for l in Path(args.codes).read_text(encoding="utf-8").splitlines() if l.strip()}
        links = [l for l in links if l["shortcode"] in keep]
    # A post the reel pipeline already analysed (for /reel, /repost-profile or an earlier audit) is reused as it is:
    # rerunning would repeat the OCR and the Gemini call for nothing.
    run_dir = PROJECT / "batch" / f"audit_{user}"
    run_dir.mkdir(parents=True, exist_ok=True)
    results = run_dir / "results.jsonl"
    done = {json.loads(l)["shortcode"] for l in results.read_text(encoding="utf-8").splitlines() if l.strip()} if results.exists() else set()
    reused = 0
    with results.open("a", encoding="utf-8") as f:
        for l in links:
            b = CACHE / l["shortcode"] / "bundle.json"
            if l["shortcode"] in done or not b.exists():
                continue
            speech = (json.loads(b.read_text(encoding="utf-8")).get("speech") or {})
            if str(speech.get("source") if isinstance(speech, dict) else "").startswith("NOT"):
                continue
            f.write(json.dumps({"shortcode": l["shortcode"], "status": "ok", "reused": True,
                                "bundle": str(CACHE / l["shortcode"] / "bundle.md")}) + "\n")
            reused += 1
    if reused:
        print(f"reused {reused} posts already analysed by the reel pipeline", flush=True)
    todo = R / "pipeline_links.json"
    todo.write_text(json.dumps(links, ensure_ascii=False), encoding="utf-8")
    cookies = cookies_path(None, user)
    os.environ["AUDIT_COOKIES"] = str(cookies)
    from reel import common, download
    common.COOKIES = download.COOKIES = cookies
    batch.PACE_SECONDS = tuple(CONFIG["pace"][a.get("pace", "normal")]["download"])
    batch.init_worker = init_worker
    print(f"pipeline for @{user}: {len(links)} posts, cookies {cookies.name}, pause {batch.PACE_SECONDS}", flush=True)
    sys.argv = ["batch.py", str(todo), "--workers", str(args.workers), "--run", f"audit_{user}"]
    batch.main()


if __name__ == "__main__":
    main()
