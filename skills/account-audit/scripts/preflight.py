"""Check everything the audit needs before it starts, and say plainly what is missing.

usage: python preflight.py [--cookies PATH]
Prints one line per check (OK / MISSING / WARN) and exits 1 if a required piece is missing.
"""
import argparse
import importlib
import shutil
import sys
from pathlib import Path

from common import CONFIG, PROJECT, CollectError, call, cookies_path, session

REQUIRED, OPTIONAL = [], []


def check(name, ok, fix, required=True):
    (REQUIRED if required else OPTIONAL).append(ok)
    print(f"{'OK     ' if ok else ('MISSING' if required else 'WARN   ')} {name}" + ("" if ok else f": {fix}"), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookies")
    args = ap.parse_args()
    reel_skill = Path.home() / ".claude" / "skills" / "reel" / "SKILL.md"
    check("reel skill", reel_skill.exists(), "install the /reel skill first; this audit runs every post through it")
    for f in ("reel.py", "batch.py", "look.py", "reel/pipeline.py"):
        check(f"reel pipeline {f}", (PROJECT / f).exists(), f"expected at {PROJECT / f}")
    for mod in ("requests", "cv2", "numpy", "onnxruntime", "fitz", "markdown", "bs4", "google.genai"):
        try:
            importlib.import_module(mod)
            check(f"python package {mod}", True, "")
        except Exception:
            check(f"python package {mod}", False, f"pip install {mod.replace('fitz', 'pymupdf').replace('bs4', 'beautifulsoup4').replace('cv2', 'opencv-python').replace('google.genai', 'google-genai')}")
    try:
        importlib.import_module("playwright")
        check("playwright (refreshing query ids)", True, "")
    except Exception:
        check("playwright (refreshing query ids)", False, "pip install playwright; only needed if Instagram changes its query ids", False)
    check("ffmpeg", bool(shutil.which("ffmpeg")), "install ffmpeg and put it on PATH")
    check("Chromium browser for PDFs (Edge or Chrome)", Path(CONFIG["edge"]).exists(), f"edit 'edge' in config.json (now {CONFIG['edge']})")
    models = Path(CONFIG["face_models"]).expanduser()
    check("face models (optional stage)", (models / "det_10g.onnx").exists() and (models / "w600k_r50.onnx").exists(),
          f"InsightFace buffalo_l det_10g.onnx and w600k_r50.onnx in {models}; without them the faces stage is skipped", False)
    try:
        sys.path.insert(0, str(PROJECT))
        from reel.speech import _skill
        keys = _skill().load_keys()
        check("Gemini keys (speech, delivery)", bool(keys), "set GEMINI_API_KEY, or one key per line in ~/.config/reel/gemini_keys.txt", True)
    except Exception as e:
        check("Gemini keys (speech, delivery)", False, f"{type(e).__name__}: {str(e)[:120]}")
    path = cookies_path(args.cookies)
    try:
        s = session(args.cookies)
        r = call(s, "GET", "https://www.instagram.com/web/search/topsearch/?query=instagram",
                 headers={"referer": "https://www.instagram.com/"})
        check(f"Instagram login ({path})", r.status_code == 200 and "users" in r.text, "export the cookies again while logged in")
    except CollectError as e:
        check(f"Instagram login ({path})", False, str(e))
    print("READY" if all(REQUIRED) else "NOT READY")
    sys.exit(0 if all(REQUIRED) else 1)


if __name__ == "__main__":
    main()
