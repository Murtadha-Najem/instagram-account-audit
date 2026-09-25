"""Who appears in an account's posts: face detection, embeddings, references, recurring people. Fully local.

Models: InsightFace buffalo_l, SCRFD det_10g (detection + 5 landmarks) and ArcFace w600k_r50 (512-d embedding),
run through onnxruntime directly. The insightface package itself is not imported: its scikit-image dependency is
built against numpy 1.x and fails to import in this environment.

usage (run from the skill's scripts folder):
  python faces.py <user> extract [CODE ...]  frames at 2 fps from the pipeline's video plus every image, per finished post;
                                             writes audit/faces/<code>.npz and <code>.json; resumable
  python faces.py <user> register            one reference per person named in account.json "team" (reference_posts),
                                             from the dominant face of those posts; review crops in faces/reference_review/
  python faces.py <user> unknowns            groups the faces that match no reference into recurring people P1, P2, ...
                                             and writes faces/unknowns.jpg to show the user for naming
  python faces.py <user> match               labels every detection (references, then named or unnamed recurring people);
                                             writes faces/matches.json
Everything works with no references at all: the recurring people are then the whole result.
Names given for recurring people go in account.json "face_names" ({"P3": "name"}); rerunning "unknowns" renumbers them,
so name them only after the last run.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from common import CACHE, CONFIG, PROJECT, account, root

F = CONFIG["faces"]
MODELS = Path(CONFIG["face_models"]).expanduser()
FPS = F["fps"]
MIN_SCORE = F["min_score"]
MIN_SIDE = F["min_side"]   # pixels, smaller faces embed poorly
MATCH = F["match"]         # cosine similarity to accept a match
MARGIN = F["margin"]       # best match must beat the runner-up by this much
OUT = None                 # set per account in main()
REFERENCES = {}
ARCFACE_DST = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                        [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)


class Models:
    def __init__(self):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        self.det = ort.InferenceSession(str(MODELS / "det_10g.onnx"), opts, providers=["CPUExecutionProvider"])
        self.rec = ort.InferenceSession(str(MODELS / "w600k_r50.onnx"), opts, providers=["CPUExecutionProvider"])
        self.det_in = self.det.get_inputs()[0].name
        self.rec_in = self.rec.get_inputs()[0].name

    def detect(self, img, size=640):
        h, w = img.shape[:2]
        scale = size / max(h, w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        canvas = np.zeros((size, size, 3), dtype=np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128, (size, size), (127.5, 127.5, 127.5), swapRB=True)
        outs = self.det.run(None, {self.det_in: blob})
        boxes, kpss, scores = [], [], []
        for i, stride in enumerate((8, 16, 32)):
            sc, bb, kp = outs[i].reshape(-1), outs[i + 3].reshape(-1, 4) * stride, outs[i + 6].reshape(-1, 10) * stride
            fh, fw = size // stride, size // stride
            centers = np.stack(np.mgrid[:fh, :fw][::-1], axis=-1).astype(np.float32).reshape(-1, 2) * stride
            centers = np.repeat(centers, 2, axis=0)
            keep = np.where(sc >= MIN_SCORE)[0]
            if not len(keep):
                continue
            c = centers[keep]
            b = np.stack([c[:, 0] - bb[keep, 0], c[:, 1] - bb[keep, 1], c[:, 0] + bb[keep, 2], c[:, 1] + bb[keep, 3]], 1)
            k = np.concatenate([np.stack([c[:, 0] + kp[keep, j], c[:, 1] + kp[keep, j + 1]], 1) for j in range(0, 10, 2)], 1)
            boxes.append(b), kpss.append(k), scores.append(sc[keep])
        if not boxes:
            return []
        boxes, kpss, scores = np.concatenate(boxes) / scale, np.concatenate(kpss) / scale, np.concatenate(scores)
        idx = cv2.dnn.NMSBoxes([[float(x1), float(y1), float(x2 - x1), float(y2 - y1)] for x1, y1, x2, y2 in boxes],
                               scores.tolist(), MIN_SCORE, 0.4)
        idx = np.array(idx).reshape(-1)
        return [(boxes[i], kpss[i].reshape(5, 2), float(scores[i])) for i in idx]

    def embed(self, img, kps):
        m, _ = cv2.estimateAffinePartial2D(kps.astype(np.float32), ARCFACE_DST, method=cv2.LMEDS)
        face = cv2.warpAffine(img, m, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(face, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        v = self.rec.run(None, {self.rec_in: blob})[0][0]
        return v / np.linalg.norm(v), face


def frames(code):
    d = CACHE / code
    if (d / "video.mp4").exists():
        cap = cv2.VideoCapture(str(d / "video.mp4"))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, int(round(fps / FPS)))
        for i in range(0, n, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, img = cap.read()
            if ok:
                yield f"video@{i / fps:.1f}", img
        cap.release()
    for f in sorted((d / "images").glob("*")) if (d / "images").exists() else []:
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            img = cv2.imread(str(f))
            if img is not None:
                yield f"image@{f.name}", img
    for f in sorted(d.glob("*.mp4")):
        if f.name != "video.mp4":   # carousel video slides, if the downloader kept them separately
            cap = cv2.VideoCapture(str(f))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            for i in range(0, n, max(1, int(round(fps / FPS)))):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ok, img = cap.read()
                if ok:
                    yield f"{f.stem}@{i / fps:.1f}", img
            cap.release()


def sharpness(face):
    return float(cv2.Laplacian(cv2.cvtColor(face, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def extract(models, code, keep_crops=False):
    OUT.mkdir(parents=True, exist_ok=True)
    dets, embs, crops = [], [], []
    for where, img in frames(code):
        for box, kps, score in models.detect(img):
            side = float(min(box[2] - box[0], box[3] - box[1]))
            if side < MIN_SIDE:
                continue
            v, face = models.embed(img, kps)
            dets.append({"where": where, "box": [round(float(x)) for x in box], "score": round(score, 3),
                         "side": round(side), "sharp": round(sharpness(face), 1)})
            embs.append(v.astype(np.float16))
            if keep_crops:
                crops.append(face)
    np.savez_compressed(OUT / f"{code}.npz", emb=np.array(embs, dtype=np.float16).reshape(-1, 512))
    (OUT / f"{code}.json").write_text(json.dumps({"shortcode": code, "detections": dets}, ensure_ascii=False), encoding="utf-8")
    return dets, np.array(embs, dtype=np.float32).reshape(-1, 512), crops


def load(code):
    d = json.loads((OUT / f"{code}.json").read_text(encoding="utf-8"))["detections"]
    return d, np.load(OUT / f"{code}.npz")["emb"].astype(np.float32)


def cluster(embs, thr=0.5):
    """Greedy online clustering on cosine similarity to running centroids."""
    labels, cents, counts = [], [], []
    for v in embs:
        if cents:
            sims = np.array(cents) @ v
            j = int(sims.argmax())
            if sims[j] >= thr:
                counts[j] += 1
                c = cents[j] * (counts[j] - 1) + v
                cents[j] = c / np.linalg.norm(c)
                labels.append(j)
                continue
        cents.append(v.copy()), counts.append(1), labels.append(len(cents) - 1)
    return np.array(labels), np.array(cents), np.array(counts)


def register(models):
    if not REFERENCES:
        print("no reference posts in account.json: nothing to register (recurring people still work)")
        np.savez(OUT / "references.npz", names=np.array([], dtype=str), emb=np.zeros((0, 512), np.float32))
        return
    refs, info = {}, {}
    review = OUT / "reference_review"
    review.mkdir(parents=True, exist_ok=True)
    for name, codes in REFERENCES.items():
        per_code = []
        for code in codes:
            if not (OUT / f"{code}.npz").exists():
                extract(models, code)
            d, e = load(code)
            if not len(e):
                print(f"{name}: no face found in {code}")
                continue
            lab, cents, counts = cluster(e)
            j = int(counts.argmax())
            per_code.append((code, d, e, lab == j, cents[j], counts, len(e)))
        if not per_code:
            continue
        # With two reels, the reference is the pair of dominant clusters that agree; one reel, its dominant cluster.
        if len(per_code) > 1:
            agree = float(per_code[0][4] @ per_code[1][4])
            info.setdefault(name, {})["dominant_clusters_agree"] = round(agree, 3)
        vecs = np.concatenate([e[m] for _, _, e, m, _, _, _ in per_code])
        c = vecs.mean(0)
        refs[name] = c / np.linalg.norm(c)
        info.setdefault(name, {}).update({
            "reels": codes, "faces_used": int(len(vecs)),
            "per_reel": [{"shortcode": code, "faces": n, "dominant": int(m.sum()), "clusters": int(len(cnt)),
                          "cluster_sizes": sorted(cnt.tolist(), reverse=True)[:5]} for code, _, _, m, _, cnt, n in per_code]})
        # Review sheet: the sharpest faces of the dominant cluster, re-cut from the frames.
        best = []
        for code, d, e, m, *_ in per_code:
            best += [(d[i]["sharp"] * (d[i]["side"] ** 0.5), code, d[i]) for i in np.where(m)[0]]
        best.sort(key=lambda x: -x[0])
        tiles = [crop_for(code, det) for _, code, det in best[:8]]
        tiles = [t for t in tiles if t is not None]
        if tiles:
            cv2.imwrite(str(review / f"{name}.jpg"), np.concatenate(tiles, axis=1))
        print(name, json.dumps(info[name], ensure_ascii=False))
    names = list(refs)
    sim = np.array([refs[a] for a in names]) @ np.array([refs[a] for a in names]).T
    np.savez(OUT / "references.npz", names=np.array(names), emb=np.array([refs[n] for n in names]))
    (OUT / "references.json").write_text(json.dumps({"people": info, "similarity_between_references":
                                                     {a: {b: round(float(sim[i, j]), 3) for j, b in enumerate(names) if b != a}
                                                      for i, a in enumerate(names)}}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("max similarity between two different people:", round(float((sim - np.eye(len(names)) * 2).max()), 3))


def crop_for(code, det):
    where = det["where"]
    kind, _, pos = where.partition("@")
    d = CACHE / code
    if kind == "video":
        cap = cv2.VideoCapture(str(d / "video.mp4"))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(pos) * 1000)
        ok, img = cap.read()
        cap.release()
        if not ok:
            return None
    elif kind == "image":
        img = cv2.imread(str(d / "images" / pos))
    else:
        return None
    x1, y1, x2, y2 = det["box"]
    pad = int(0.25 * (x2 - x1))
    h, w = img.shape[:2]
    face = img[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]
    return cv2.resize(face, (160, 160)) if face.size else None


def references():
    f = OUT / "references.npz"
    if not f.exists():
        return [], np.zeros((0, 512), np.float32)
    r = np.load(f)
    return [str(n) for n in r["names"]], r["emb"].astype(np.float32).reshape(-1, 512)


def gallery(acc):
    """References (kind "team"), then the recurring people: a name the user gave them, else their P number."""
    names, vecs = references()
    kinds = ["team"] * len(names)
    vecs = list(vecs)
    team = {p["name"] for p in acc["team"]}
    if (OUT / "unknowns.npz").exists():
        u = np.load(OUT / "unknowns.npz")
        for uid, v in zip(u["ids"], u["emb"]):
            uid = str(uid)
            name = acc["face_names"].get(uid, uid)
            names.append(name), vecs.append(v)
            kinds.append("team" if name in team else ("named" if uid in acc["face_names"] else "recurring"))
    return names, np.array(vecs, dtype=np.float32).reshape(-1, 512), kinds


def detection_files():
    return [f for f in sorted(OUT.glob("*.json")) if f.stem not in ("references", "matches", "unknowns")]


def match(acc):
    names, R, kinds = gallery(acc)
    kind_of = dict(zip(names, kinds))
    uniq = list(dict.fromkeys(names))
    out = {}
    for f in detection_files():
        d, e = load(f.stem)
        if not len(e) or not len(uniq):
            out[f.stem] = {"faces": int(len(e)), "matched": 0, "unidentified": int(len(e)), "people": {}}
            continue
        s = e @ R.T
        per_name = np.stack([s[:, [k for k, n in enumerate(names) if n == u]].max(1) for u in uniq], 1)
        order = np.argsort(-per_name, axis=1)
        best = per_name[np.arange(len(e)), order[:, 0]]
        second = per_name[np.arange(len(e)), order[:, 1]] if len(uniq) > 1 else np.zeros(len(e))
        ok = (best >= MATCH) & (best - second >= MARGIN)
        people = {}
        for i in np.where(ok)[0]:
            n = uniq[order[i, 0]]
            p = people.setdefault(n, {"kind": kind_of[n], "detections": 0, "best_sim": 0.0})
            p["detections"] += 1
            p["best_sim"] = round(max(p["best_sim"], float(best[i])), 3)
        out[f.stem] = {"faces": int(len(e)), "matched": int(ok.sum()), "unidentified": int((~ok).sum()), "people": people}
    (OUT / "matches.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    seen = {}
    for m in out.values():
        for n, p in m["people"].items():
            if p["detections"] >= CONFIG["analysis"]["presence_min_frames"]:
                seen[n] = seen.get(n, 0) + 1
    print(f"{len(out)} posts matched; people by number of posts: " +
          ", ".join(f"{n} {k}" for n, k in sorted(seen.items(), key=lambda x: -x[1])))


def unknowns(min_side=60, min_sharp=40, thr=0.5):
    """Group the faces that match no reference into identities across all posts, for naming by hand.
    Keeps a group seen in at least 2 posts or 20 detections, writes faces/unknowns.json and unknowns.jpg."""
    _, R = references()
    vecs, where = [], []
    for f in detection_files():
        d, e = load(f.stem)
        if not len(e):
            continue
        s = e @ R.T if len(R) else np.zeros((len(e), 1), np.float32)
        for i in range(len(e)):
            if s[i].max() < MATCH - 0.1 and d[i]["side"] >= min_side and d[i]["sharp"] >= min_sharp:
                vecs.append(e[i]), where.append((f.stem, d[i]))
    if not vecs:
        print("no unmatched faces")
        np.savez(OUT / "unknowns.npz", ids=np.array([], dtype=str), emb=np.zeros((0, 512), np.float32))
        return
    lab, cents, counts = cluster(np.array(vecs), thr)
    groups = []
    for j in np.argsort(-counts):
        idx = np.where(lab == j)[0]
        posts = sorted({where[i][0] for i in idx})
        if len(posts) < 2 and len(idx) < 20:
            continue
        best = sorted(idx, key=lambda i: -where[i][1]["sharp"] * where[i][1]["side"] ** 0.5)
        tiles, used = [], set()
        for i in best:   # one sharp tile per post first, so the sheet shows the spread
            if where[i][0] in used and len(used) < len(posts):
                continue
            t = crop_for(*where[i])
            if t is not None:
                tiles.append(t), used.add(where[i][0])
            if len(tiles) == 6:
                break
        groups.append({"id": f"P{len(groups) + 1}", "detections": int(len(idx)), "posts": posts, "tiles": tiles,
                       "centroid": cents[j]})
    sheet = []
    for g in groups:
        lab_img = np.full((160, 200, 3), 255, np.uint8)
        cv2.putText(lab_img, g["id"], (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        cv2.putText(lab_img, f"{len(g['posts'])} posts", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
        row = np.concatenate([lab_img] + g["tiles"] + [np.full((160, 160, 3), 255, np.uint8)] * (6 - len(g["tiles"])), 1)
        sheet.append(row)
    if sheet:
        cv2.imwrite(str(OUT / "unknowns.jpg"), np.concatenate(sheet, 0))
    np.savez(OUT / "unknowns.npz", ids=np.array([g["id"] for g in groups]), emb=np.array([g["centroid"] for g in groups]))
    (OUT / "unknowns.json").write_text(json.dumps([{k: v for k, v in g.items() if k not in ("tiles", "centroid")} for g in groups],
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(vecs)} unmatched good faces -> {len(groups)} recurring unknown people")
    for g in groups:
        print(g["id"], g["detections"], len(g["posts"]), g["posts"][:8])


def main():
    global OUT, REFERENCES
    if len(sys.argv) < 3:
        print(__doc__)
        return
    user, cmd = sys.argv[1].lstrip("@").lower(), sys.argv[2]
    acc = account(user)
    R = root(user)
    OUT = R / "faces"
    OUT.mkdir(exist_ok=True)
    REFERENCES = {p["name"]: p["reference_posts"] for p in acc["team"] if p.get("reference_posts")}
    if cmd == "unknowns":
        return unknowns()
    if cmd == "extract":
        models = Models()
        codes = sys.argv[3:] or [l["shortcode"] for l in json.loads((R / "links.json").read_text(encoding="utf-8"))]
        results = PROJECT / "batch" / f"audit_{user}" / "results.jsonl"
        finished = {json.loads(l)["shortcode"] for l in results.read_text(encoding="utf-8").splitlines() if l.strip()} \
            if results.exists() else set()
        for n, code in enumerate(codes, 1):
            if (OUT / f"{code}.npz").exists():
                continue
            if code not in finished and not sys.argv[3:]:   # still downloading or analysing: a half-written video
                continue
            if not (CACHE / code).exists():
                continue
            d, _, _ = extract(models, code)
            print(f"[{n}/{len(codes)}] {code}: {len(d)} faces", flush=True)
    elif cmd == "register":
        register(Models())
    elif cmd == "match":
        match(acc)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
