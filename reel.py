"""Turn an Instagram reel or post link into a compact bundle for Claude.

usage: python reel.py <instagram url> [--force-transcribe] [--refresh] [--max-frames N] [--dense]
"""
import argparse
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from reel.common import CACHE_ROOT, ReelError  # noqa: E402
from reel.pipeline import process  # noqa: E402

CACHE_DAYS = 30


def prune_cache():
    if not CACHE_ROOT.exists():
        return
    cutoff = time.time() - CACHE_DAYS * 86400
    for d in CACHE_ROOT.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--force-transcribe", action="store_true", help="transcribe even if captions cover the speech")
    ap.add_argument("--refresh", action="store_true", help="download again instead of using the cache")
    ap.add_argument("--max-frames", type=int, default=8)
    ap.add_argument("--dense", action="store_true",
                    help="send every visually distinct frame instead of one per camera shot (for product reveals, props, gestures)")
    args = ap.parse_args()

    # Automatic 30-day deletion is off: data/cache is now the permanent store. What to delete is decided later.
    result = process(args.url, force_transcribe=args.force_transcribe, refresh=args.refresh,
                     max_frames=args.max_frames, dense=args.dense)
    print(result["bundle"])


if __name__ == "__main__":
    try:
        main()
    except ReelError as e:
        print(f"REEL ERROR: {e}", file=sys.stderr)
        sys.exit(1)
