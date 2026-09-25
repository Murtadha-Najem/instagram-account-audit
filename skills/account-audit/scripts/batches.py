"""Hand posts to the agents: the profiler's sample, then the content and craft waves, in balanced batches.

usage:
  python batches.py <user> sample [--n 20]      picks a spread of posts for the profiler (types, time, strong and weak);
                                                writes audit/profile_sample.txt (codes, for run_pipeline.py --codes)
                                                and profile_sample.json (what the profiler reads)
  python batches.py <user> content [--flush]    content-coding batches from posts the pipeline has finished
  python batches.py <user> craft [--flush] [--sample N] [--basics]
                                                craft-review batches; --sample N reviews a stratified sample only
                                                (brief mode, very large accounts); --basics makes the craft agents also
                                                write the content basics (content-only mode, no content wave)
  add --reassign to hand out again posts that were assigned but never finished,
  and --allow-untranscribed to hand out posts whose speech Gemini could not transcribe.
Batches are about 35 weight units (reel 3, carousel 1.5 to 2, photo 1); without --flush only full batches are made, so the
command can be repeated while the pipeline runs.
"""
import argparse
import json
from pathlib import Path

from common import CACHE, PROJECT, root, username_from

WEIGHT = {"content": {"reel": 3.0, "carousel": 1.5, "photo": 1.0, "video": 3.0},
          "craft": {"reel": 3.0, "carousel": 2.0, "photo": 1.0, "video": 3.0}}
TARGET = 35.0


def parses(path, key):
    try:
        return bool(json.loads(Path(path).read_text(encoding="utf-8")).get(key))
    except Exception:
        return False


def pipeline_state(user):
    ok, failed = set(), {}
    f = PROJECT / "batch" / f"audit_{user}" / "results.jsonl"
    for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []):
        if line.strip():
            row = json.loads(line)
            if row.get("status") == "ok":
                ok.add(row["shortcode"])
                failed.pop(row["shortcode"], None)
            elif row["shortcode"] not in ok:
                failed[row["shortcode"]] = row.get("error", "")
    return ok, failed


def untranscribed(code):
    b = CACHE / code / "bundle.json"
    src = ((json.loads(b.read_text(encoding="utf-8")) if b.exists() else {}).get("speech") or {}).get("source") or ""
    return str(src).startswith("NOT")


def spread(items, k):
    """k items evenly spaced through a list."""
    if k >= len(items):
        return list(items)
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def sample(user, n):
    R = root(user)
    links = json.loads((R / "links.json").read_text(encoding="utf-8"))
    by_type = {}
    for l in links:
        by_type.setdefault(l["type"], []).append(l)
    picked = []
    for t, ls in by_type.items():
        k = max(1, round(n * len(ls) / len(links)))
        key = (lambda l: l.get("plays") or 0) if t == "reel" else (lambda l: l.get("likes") or 0)
        ranked = sorted(ls, key=key)
        extremes = ranked[-2:] + ranked[:1]            # the two strongest and the weakest of the type
        rest = [l for l in spread(ls, k) if l not in extremes]
        picked += extremes + rest[:max(0, k - len(extremes))]
    picked = sorted({l["shortcode"]: l for l in picked}.values(), key=lambda l: l["taken_at"])
    raw = {}
    for name in ("posts_raw.jsonl", "reels_raw.jsonl"):
        f = R / name
        for line in (open(f, encoding="utf-8") if f.exists() else []):
            if line.strip():
                x = json.loads(line)
                raw.setdefault(x["code"], x)
    out = [{"shortcode": l["shortcode"], "type": l["type"], "posted": l["taken_at"], "plays": l.get("plays"), "likes": l.get("likes"),
            "comments": l.get("comments"), "coauthors": l.get("coauthors"),
            "caption": (((raw.get(l["shortcode"]) or {}).get("caption") or {}).get("text") or "")[:600],
            "bundle": str(CACHE / l["shortcode"] / "bundle.md")} for l in picked]
    (R / "profile_sample.txt").write_text("\n".join(o["shortcode"] for o in out), encoding="utf-8")
    (R / "profile_sample.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"profiler sample: {len(out)} posts -> {R / 'profile_sample.txt'}")


def people(R, code):
    f = R / "faces" / "matches.json"
    m = (json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}).get(code) or {}
    return {"on_screen": {n: p["detections"] for n, p in (m.get("people") or {}).items() if p["detections"] >= 3},
            "unidentified_faces": m.get("unidentified", 0),
            "note": "frames at 2 per second; P numbers are recurring people nobody has named"}


def stratified(user, codes, n):
    """Strongest, weakest and typical posts of each type, spread in time, by lift when dataset.json exists."""
    R = root(user)
    ds = R / "analysis" / "dataset.json"
    rows = {r["shortcode"]: r for r in json.loads(ds.read_text(encoding="utf-8"))} if ds.exists() else {}
    links = {l["shortcode"]: l for l in json.loads((R / "links.json").read_text(encoding="utf-8"))}
    by_type = {}
    for c in codes:
        by_type.setdefault(links[c]["type"], []).append(c)
    picked = []
    for t, cs in by_type.items():
        k = max(2, round(n * len(cs) / len(codes)))
        score = lambda c: (rows.get(c) or {}).get("perf_lift") or (links[c].get("plays") or links[c].get("likes") or 0)  # noqa: E731
        ranked = sorted(cs, key=score)
        third = max(1, k // 3)
        chosen = ranked[-third:] + ranked[:third]
        middle = [c for c in spread(sorted(cs, key=lambda c: links[c]["taken_at"]), k) if c not in chosen]
        picked += chosen + middle[:k - len(chosen)]
    return list(dict.fromkeys(picked))


def make(user, wave, flush, reassign, allow_untranscribed, sample_n, basics):
    R = root(user)
    A = R / "analysis"
    links = json.loads((R / "links.json").read_text(encoding="utf-8"))
    ok, failed = pipeline_state(user)
    for d in ("records", "coding", "craft", "craft_notes", f"batches_{wave}"):
        (A / d).mkdir(parents=True, exist_ok=True)
    assigned_f = A / f"batches_{wave}" / "assigned.json"
    assigned = set(json.loads(assigned_f.read_text(encoding="utf-8"))) if assigned_f.exists() else set()
    codes = [l["shortcode"] for l in links]
    if sample_n:
        codes = stratified(user, codes, sample_n)
        (A / "craft_sample.txt").write_text("\n".join(codes), encoding="utf-8")
    types = {l["shortcode"]: l["type"] for l in links}
    pending, held = [], []
    for code in codes:
        if code not in ok:
            continue
        if wave == "content" and parses(A / "coding" / f"{code}.json", "digest"):
            continue
        if wave == "craft" and parses(A / "craft" / f"{code}.json", "top_fixes"):
            continue
        if code in assigned and not reassign:
            continue
        if untranscribed(code) and not allow_untranscribed:
            held.append(code)
            continue
        slides = CACHE / code / "slides" / "transcripts.json"
        delivery = R / "delivery" / f"{code}.json"
        e = {"shortcode": code, "type": types[code], "bundle": str(CACHE / code / "bundle.md"),
             "extra_transcripts": str(slides) if slides.exists() else None,
             "delivery": str(delivery) if delivery.exists() else None}
        if wave == "content":
            cf = R / "comments" / f"{code}.json"
            cm = json.loads(cf.read_text(encoding="utf-8"))["comments"] if cf.exists() else []
            e.update({"people": people(R, code),
                      "comments": [{"id": c["id"], "reply_to": c["parent"], "by_account": c["is_account"], "text": c["text"]} for c in cm][:300],
                      "record": str(A / "records" / f"{code}.md"), "coding": str(A / "coding" / f"{code}.json")})
        else:
            first = A / "coding" / f"{code}.json"
            e.update({"people": people(R, code), "basics": basics,
                      "first_pass": str(first) if first.exists() else None,
                      "record": str(A / "records" / f"{code}.md") if (A / "records" / f"{code}.md").exists() else None,
                      "craft": str(A / "craft" / f"{code}.json"), "craft_notes": str(A / "craft_notes" / f"{code}.md")})
        pending.append(e)
    w = WEIGHT[wave]
    pending.sort(key=lambda e: -w.get(e["type"], 1))
    total = sum(w.get(e["type"], 1) for e in pending)
    made = []
    if total >= TARGET or (flush and pending):
        nbins = max(1, min(10, round(total / TARGET))) if flush else max(1, int(total // TARGET))
        bins, loads = [[] for _ in range(nbins)], [0.0] * nbins
        for e in pending:
            k = loads.index(min(loads))
            bins[k].append(e)
            loads[k] += w.get(e["type"], 1)
        existing = len(list((A / f"batches_{wave}").glob("batch_*.json")))
        for i, b in enumerate(bins, 1):
            path = A / f"batches_{wave}" / f"batch_{existing + i:02d}.json"
            path.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
            assigned.update(e["shortcode"] for e in b)
            made.append(path)
            print(f"{path} ({len(b)} posts, {sum(1 for e in b if e['type'] == 'reel')} reels)")
        pending = []
    assigned_f.write_text(json.dumps(sorted(assigned)), encoding="utf-8")
    done = sum(1 for c in codes if parses(A / ("coding" if wave == "content" else "craft") / f"{c}.json",
                                         "digest" if wave == "content" else "top_fixes"))
    print(f"{wave}: posts {len(codes)} | pipeline ok {len([c for c in codes if c in ok])} | failed {len(failed)} | done {done} | "
          f"waiting {len(pending)} | new batches {len(made)}")
    if held:
        print(f"  held back, speech not transcribed (retry with reel.py, or --allow-untranscribed): {' '.join(held)}")
    for code, err in failed.items():
        print(f"  pipeline failed: {code}: {err[:150]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("wave", choices=["sample", "content", "craft"])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--flush", action="store_true")
    ap.add_argument("--reassign", action="store_true")
    ap.add_argument("--allow-untranscribed", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--basics", action="store_true")
    args = ap.parse_args()
    user = username_from(args.profile)
    if args.wave == "sample":
        sample(user, args.n)
    else:
        make(user, args.wave, args.flush, args.reassign, args.allow_untranscribed, args.sample, args.basics)


if __name__ == "__main__":
    main()
