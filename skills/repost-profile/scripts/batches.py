"""Hand processed posts to the watch-and-code agents in batches, as they become ready.

A post is ready when the pipeline run holds an ok result for it. A post is done when both its record and its coding
file exist and the coding parses. Posts already handed out (work/assigned.json) are not handed out again unless
--reassign is given, so this can be called repeatedly while the pipeline is still running.

usage: python batches.py <profile dir> [--size 25] [--flush] [--reassign]
prints one line per new batch file; --flush also releases a final batch smaller than --size
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
PROJECT = Path(CONFIG["project_root"])
CACHE = PROJECT / "data" / "cache"


def post_meta(code):
    d = CACHE / code
    if (d / "metadata.json").exists():
        return json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    if (d / "post.json").exists():
        return json.loads((d / "post.json").read_text(encoding="utf-8")).get("details") or {}
    return {}


def coded(path):
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile_dir")
    ap.add_argument("--size", type=int, default=25)
    ap.add_argument("--flush", action="store_true")
    ap.add_argument("--reassign", action="store_true", help="hand out again posts that were assigned but never finished")
    ap.add_argument("--allow-untranscribed", action="store_true", help="hand out posts whose speech Gemini could not transcribe")
    args = ap.parse_args()

    p = Path(args.profile_dir)
    profile = json.loads((p / "profile.json").read_text(encoding="utf-8"))
    links = json.loads((p / "links.json").read_text(encoding="utf-8"))
    results = PROJECT / "batch" / f"profile_{profile['username'].lower()}" / "results.jsonl"
    ok, failed = set(), {}
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("status") == "ok":
                    ok.add(row["shortcode"])
                    failed.pop(row["shortcode"], None)
                elif row["shortcode"] not in ok:
                    failed[row["shortcode"]] = row.get("error", "")
    for d in ("records", "coding", "work"):
        (p / d).mkdir(exist_ok=True)
    assigned_path = p / "work" / "assigned.json"
    assigned = set(json.loads(assigned_path.read_text(encoding="utf-8"))) if assigned_path.exists() else set()

    pending, untranscribed = [], []
    for item in links:
        code = item["shortcode"]
        if code not in ok:
            continue
        coding = p / "coding" / f"{code}.json"
        records = list((p / "records").glob(f"*_{code}.md"))
        if records and coding.exists() and coded(coding):
            continue
        if code in assigned and not args.reassign:
            continue
        bundle = CACHE / code / "bundle.json"
        speech = ((json.loads(bundle.read_text(encoding="utf-8")) if bundle.exists() else {}).get("speech") or {}).get("source") or ""
        if speech.startswith("NOT") and not args.allow_untranscribed:
            untranscribed.append(code)
            continue
        meta = post_meta(code)
        owner = re.sub(r"[^A-Za-z0-9_.]", "", ((meta.get("owner") or {}).get("username") or item.get("owner") or "unknown"))
        posted = (meta.get("posted_utc") or "0000-00-00")[:10]
        pending.append({"order": item["order"], "shortcode": code, "bundle": str(CACHE / code / "bundle.md"),
                        "record": str(p / "records" / f"{posted}_{owner}_{code}.md"), "coding": str(coding),
                        "repost_note": item.get("note_text") or ""})

    existing = sorted(p.glob("work/batch_*.json"))
    n = len(existing)
    made = 0
    while len(pending) >= args.size or (args.flush and pending):
        chunk, pending = pending[:args.size], pending[args.size:]
        n += 1
        path = p / "work" / f"batch_{n:02d}.json"
        path.write_text(json.dumps(chunk, ensure_ascii=False, indent=1), encoding="utf-8")
        assigned.update(x["shortcode"] for x in chunk)
        made += 1
        print(f"{path} ({len(chunk)} posts)")
    assigned_path.write_text(json.dumps(sorted(assigned)), encoding="utf-8")

    done = sum(1 for item in links if (p / "coding" / f"{item['shortcode']}.json").exists())
    print(f"links {len(links)} | pipeline ok {len(ok)} | failed {len(failed)} | coded {done} | "
          f"waiting for a full batch {len(pending)} | new batches {made}")
    if untranscribed:
        print(f"  held back, speech not transcribed (retry later with reel.py, or pass --allow-untranscribed): {' '.join(untranscribed)}")
    for code, err in failed.items():
        print(f"  pipeline failed: {code}: {err[:150]}")


if __name__ == "__main__":
    main()
