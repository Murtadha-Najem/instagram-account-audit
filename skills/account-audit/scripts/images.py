"""Cut the example images the report shows: the frames and slides the craft reviewers named as exhibits, plus any extra
frame asked for by hand.

usage: python images.py <user>                      every exhibit in analysis/craft/*.json
       python images.py <user> CODE video@3.5 ...  extra frames (or image@img_02.jpg)
writes analysis/img/<code>_<n>.jpg (480 px wide) and analysis/img/index.json {file: {code, source, kind, shows}}
"""
import json
import sys
from pathlib import Path

import cv2

from common import CACHE, root

WIDTH = 480
A = OUT = None


def grab(code, source):
    kind, _, pos = source.partition("@")
    cache = CACHE / code
    if kind == "video":
        cap = cv2.VideoCapture(str(cache / "video.mp4"))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(pos) * 1000)
        ok, img = cap.read()
        cap.release()
        return img if ok else None
    if kind == "image":
        f = cache / "images" / pos
        if not f.exists():   # reviewers sometimes write image_01.jpg for img_01.jpg
            alt = sorted((cache / "images").glob(f"*{''.join(ch for ch in pos if ch.isdigit())[-2:]}.jpg"))
            f = alt[0] if alt else f
        return cv2.imread(str(f)) if f.exists() else None
    return None


def save(code, source, n, meta, index):
    img = grab(code, source)
    if img is None:
        print(f"  {code} {source}: not found")
        return
    h, w = img.shape[:2]
    img = cv2.resize(img, (WIDTH, int(h * WIDTH / w)))
    name = f"{code}_{n}.jpg"
    cv2.imwrite(str(OUT / name), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    index[name] = {"code": code, "source": source, **meta}


def main():
    global A, OUT
    A = root(sys.argv[1].lstrip("@").lower()) / "analysis"
    OUT = A / "img"
    OUT.mkdir(exist_ok=True)
    sys.argv = sys.argv[1:]
    idx_f = OUT / "index.json"
    index = json.loads(idx_f.read_text(encoding="utf-8")) if idx_f.exists() else {}
    if len(sys.argv) > 2:
        code = sys.argv[1]
        for k, src in enumerate(sys.argv[2:], 1):
            save(code, src, f"x{k}", {"kind": "extra", "shows": ""}, index)
    else:
        for f in sorted((A / "craft").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for n, ex in enumerate(d.get("exhibits") or [], 1):
                if ex.get("source"):
                    save(d["shortcode"], ex["source"].strip(), n, {"kind": ex.get("kind"), "shows": ex.get("shows")}, index)
    idx_f.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(index)} images in {OUT}")


if __name__ == "__main__":
    main()
