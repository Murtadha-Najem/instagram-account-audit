"""Install the three Claude Code skills from this repository and point them at this folder.

usage: python install.py [--force] [--models] [--skills-dir PATH]
  --force        replace skills that are already installed
  --models       also download the optional models: PANNs audio tagger (about 330 MB) and InsightFace buffalo_l
                 face models (about 280 MB)
  --skills-dir   where Claude Code looks for skills (default ~/.claude/skills)

The skills are copied, not linked; run it again after pulling changes (with --force).
"""
import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
SKILLS = ("reel", "repost-profile", "account-audit")
PANNS = ("https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1", "Cnn14_mAP=0.431.pth")
PANNS_LABELS = "http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv"
BUFFALO = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"


def find_browser():
    """A Chromium browser for headless PDF printing: Edge or Chrome."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return ""


def render(text, values):
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  already there: {dest}")
        return
    print(f"  downloading {url}")
    urllib.request.urlretrieve(url, dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--skills-dir", default=str(Path.home() / ".claude" / "skills"))
    args = ap.parse_args()
    browser = find_browser()
    values = {"PROJECT_ROOT": str(REPO), "PYTHON": sys.executable, "BROWSER": browser}
    target_root = Path(args.skills_dir).expanduser()
    for name in SKILLS:
        target = target_root / name
        if target.exists() and not args.force:
            print(f"skip {name}: already installed at {target} (use --force to replace)")
            continue
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(REPO / "skills" / name, target, ignore=shutil.ignore_patterns("__pycache__"))
        for f in target.rglob("*"):
            if not f.is_file() or f.suffix not in (".md", ".json"):
                continue
            # inside JSON strings a Windows backslash must be escaped
            vals = values if f.suffix == ".md" else {k: v.replace("\\", "\\\\") for k, v in values.items()}
            f.write_text(render(f.read_text(encoding="utf-8"), vals), encoding="utf-8")
        print(f"installed {name} -> {target}")
    (Path.home() / ".config" / "reel").mkdir(parents=True, exist_ok=True)
    if args.models:
        download(PANNS[0], Path.home() / "panns_data" / PANNS[1])
        download(PANNS_LABELS, Path.home() / "panns_data" / "class_labels_indices.csv")
        faces = Path.home() / ".insightface" / "models" / "buffalo_l"
        if not (faces / "w600k_r50.onnx").exists():
            z = Path.home() / ".insightface" / "models" / "buffalo_l.zip"
            download(BUFFALO, z)
            faces.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(z) as zf:
                for member in zf.namelist():
                    if member.endswith(".onnx"):
                        (faces / Path(member).name).write_bytes(zf.read(member))
            z.unlink()
    print("\nNext:")
    print(f"  1. pip install -r {REPO / 'requirements.txt'}   (and ffmpeg on PATH)")
    print("  2. export Instagram cookies (extension 'Get cookies.txt LOCALLY', while logged in) to ~/.config/reel/cookies.txt")
    print("  3. set GEMINI_API_KEY, or put one key per line in ~/.config/reel/gemini_keys.txt")
    if not browser:
        print("  4. no Edge or Chrome found: set \"edge\" in the two skills' scripts/config.json to a Chromium browser")
    if not args.models:
        print("  optional: python install.py --models  (audio tagger and face models)")


if __name__ == "__main__":
    main()
