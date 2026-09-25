"""Process a list of Instagram links in parallel and measure every stage.

One downloader works through the list with a pause between fresh downloads: parallel downloads from one
logged-in account look automated and risk Instagram restricting it. Each finished download goes straight to
a pool of analysis workers; each worker loads the audio model and OCR engines once and shares the CPU.
Gemini and Shazam calls are capped across all workers. The run is resumable: finished links are skipped.

usage: python batch.py <links.json> [--workers 3] [--run NAME] [--gemini-concurrency 3] [--limit N]
links.json: a list of {"href": ..., "shortcode": ..., ...} (extra fields are carried into the results)
"""
import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, wait
from datetime import datetime
from multiprocessing import Manager
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PACE_SECONDS = (4.0, 9.0)      # pause after each fresh download
STOP_HINTS = ("wants a login", "refused the cookies")


def init_worker(threads, gemini_limit, shazam_limit):
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[var] = str(threads)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import torch
    torch.set_num_threads(threads)
    from reel import audio, speech, video
    video.OCR_THREADS = threads
    speech.GEMINI_LIMIT = gemini_limit
    audio.SHAZAM_LIMIT = shazam_limit


def analyse(item):
    from reel.pipeline import process
    started = time.time()
    try:
        return {"status": "ok", **process(item["href"])}
    except Exception as e:  # one bad link must not stop the batch
        return {"status": "error", "shortcode": item["shortcode"], "error": f"{type(e).__name__}: {str(e)[:300]}",
                "total_s": round(time.time() - started, 1)}


def load_done(results):
    done = {}
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("status") == "ok":
                    done[row["shortcode"]] = row
    return done


def summarise(rows, wall_s, workers):
    ok = [r for r in rows if r.get("status") == "ok"]
    total = lambda key: round(sum(r.get(key) or 0 for r in ok), 1)  # noqa: E731
    count = lambda key: {v: sum(1 for r in ok if r.get(key) == v) for v in sorted({str(r.get(key)) for r in ok})}  # noqa: E731
    return {
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "workers": workers,
        "links": len(rows), "ok": len(ok), "errors": len(rows) - len(ok),
        "wall_clock_s_this_run": round(wall_s, 1),
        "sum_download_s": total("download_s"), "sum_video_s": total("video_s"),
        "sum_audio_s": total("audio_s"), "sum_speech_s": total("speech_s"), "sum_pipeline_s": total("total_s"),
        "gemini_calls": sum(1 for r in ok if r.get("gemini_in")),
        "gemini_tokens_in": int(total("gemini_in")), "gemini_tokens_out": int(total("gemini_out")),
        "gemini_unavailable": sum(1 for r in ok if r.get("gemini_error")),
        "frames_sent": int(total("frames_sent")),
        "claude_image_tokens_estimate": int(total("frames_sent") * 576),
        "formats": count("format"), "audio_kinds": count("audio_kind"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("links")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--run", default=datetime.now().strftime("%Y%m%d_%H%M"))
    ap.add_argument("--gemini-concurrency", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="process only the first N links (for a pilot)")
    args = ap.parse_args()

    from reel import download
    from reel.common import ReelError

    links = json.loads(Path(args.links).read_text(encoding="utf-8"))
    if args.limit:
        links = links[:args.limit]
    run_dir = ROOT / "batch" / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    results = run_dir / "results.jsonl"
    done = load_done(results)
    todo = [x for x in links if x["shortcode"] not in done]
    threads = max(1, (os.cpu_count() or 4) // args.workers)
    print(f"run {args.run}: {len(links)} links, {len(done)} already done, {len(todo)} to go, "
          f"{args.workers} workers x {threads} threads", flush=True)

    lock = threading.Lock()
    rows = list(done.values())
    started = time.time()

    def record(row):
        with lock:
            rows.append(row)
            with results.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{len(rows)}/{len(links)}] {row.get('shortcode')} {row['status']} "
                  f"{row.get('format', '')} total {row.get('total_s', 0)}s "
                  f"{row.get('error', '') or row.get('speech_source', '')}"[:200], flush=True)

    manager = Manager()
    gemini_limit, shazam_limit = manager.Semaphore(args.gemini_concurrency), manager.Semaphore(1)
    stopped = None
    with ProcessPoolExecutor(args.workers, initializer=init_worker, initargs=(threads, gemini_limit, shazam_limit)) as pool:
        futures = []
        for item in todo:
            extra = {k: v for k, v in item.items() if k not in ("href",)}
            t = time.time()
            try:
                meta = download.fetch(item["href"])
            except ReelError as e:
                record({**extra, "status": "error", "stage": "download", "error": str(e)[:300],
                        "download_s": round(time.time() - t, 1)})
                if any(h in str(e) for h in STOP_HINTS):
                    stopped = str(e)
                    break
                continue
            download_s, cached = round(time.time() - t, 1), meta["cached"]
            future = pool.submit(analyse, item)
            future.add_done_callback(lambda f, extra=extra, d=download_s, c=cached: record(
                {**extra, **f.result(), "download_s": d, "download_cached": c}))
            futures.append(future)
            if not cached:
                time.sleep(random.uniform(*PACE_SECONDS))
        wait(futures)

    summary = summarise(rows, time.time() - started, args.workers)
    if stopped:
        summary["stopped_early"] = stopped
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
