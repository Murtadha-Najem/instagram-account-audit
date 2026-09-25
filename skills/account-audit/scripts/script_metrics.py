"""Measurable features of every script and caption, counted from the transcripts rather than judged.

usage: python script_metrics.py <username>
writes audit/analysis/script_metrics.json and script_facts.md
Language-neutral where it can be: words, words per second, numbers, questions, viewer address, and the share of Latin
words inside speech that is mostly in another script (English terms in Arabic speech, for example).
"""
import json
import re
import statistics as st
import sys
from collections import Counter

from build_dataset import spearman
from common import CACHE, root

ARABIC = re.compile(r"[؀-ۿ]+")
LATIN = re.compile(r"[A-Za-z]+")
WORD = re.compile(r"\w+", re.U)
NUM = re.compile(r"\d[\d,.]*%?|مليون|مليار|ألف|الف|بالمية|بالمئة|million|billion|thousand|percent", re.I)
YOU = re.compile(r"\b(you|your|you're|yours)\b|\b(انت|إنت|انتو|إنتو|انتم|أنتم|تعرف|تعرفون|تدري|تدرون|عندك|تريد|تحتاج|لازم ت)\w*", re.I)
QUESTION = re.compile(r"[؟?]")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def speech_text(code):
    f = CACHE / code / "bundle.json"
    b = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    segs = ((b.get("speech") or {}).get("segments") or []) if isinstance(b.get("speech"), dict) else []
    text = " ".join(s.get("text", "") for s in segs)
    extra = CACHE / code / "slides" / "transcripts.json"
    if extra.exists():
        text += " " + " ".join(s.get("text", "") for sl in json.loads(extra.read_text(encoding="utf-8")) for s in sl["segments"])
    return text.strip(), b.get("duration")


def main():
    user = sys.argv[1].lstrip("@").lower()
    A = root(user) / "analysis"
    rows = json.loads((A / "dataset.json").read_text(encoding="utf-8"))
    out = {}
    for r in rows:
        code = r["shortcode"]
        text, dur = speech_text(code)
        words = len(WORD.findall(text))
        ar, en = len(ARABIC.findall(text)), len(LATIN.findall(text))
        cap = r.get("caption") or ""
        cap_ar, cap_en = len(ARABIC.findall(cap)), len(LATIN.findall(cap))
        out[code] = {
            "speech_words": words, "words_per_second": round(words / dur, 2) if words and dur and r["type"] == "reel" else None,
            "latin_share_in_speech": round(en / (ar + en), 3) if ar > en and (ar + en) else None,
            "numbers": len(NUM.findall(text)), "questions": len(QUESTION.findall(text)), "you_address": len(YOU.findall(text)),
            "caption_words": len(WORD.findall(cap)), "caption_emoji": len(EMOJI.findall(cap)),
            "caption_script": "arabic" if cap_en < 0.2 * (cap_ar + cap_en + 1) else ("latin" if cap_ar < 0.2 * (cap_ar + cap_en + 1) else "both"),
            "caption_first_line": (cap.strip().split("\n")[0] if cap.strip() else "")[:160],
            "caption_hashtags": len(re.findall(r"#\w+", cap)), "caption_mentions": len(re.findall(r"@\w+", cap)),
        }
    (A / "script_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    D = {r["shortcode"]: r for r in rows}
    judged = [c for c, r in D.items() if not r["too_recent"] and not r["boosted"]]
    reels = [c for c in judged if D[c]["type"] == "reel" and out[c]["speech_words"] > 20]
    med = lambda xs: (lambda v: st.median(v) if v else None)([x for x in xs if x is not None])  # noqa: E731
    L = ["# Script and caption metrics", ""]
    L.append(f"- Reels with speech: {len(reels)}; words median {med([out[c]['speech_words'] for c in reels])}; words per second median "
             f"{med([out[c]['words_per_second'] for c in reels])}; Latin-word share in non-Latin speech median {med([out[c]['latin_share_in_speech'] for c in reels])}")
    L.append(f"- Numbers per reel median {med([out[c]['numbers'] for c in reels])}; reels with no number {sum(1 for c in reels if out[c]['numbers'] == 0)}; "
             f"reels that address the viewer {sum(1 for c in reels if out[c]['you_address'] > 0)}; with a question {sum(1 for c in reels if out[c]['questions'])}")
    L.append("\n| feature (reels) | rho with lift | n |\n|---|---|---|")
    for k in ("speech_words", "words_per_second", "latin_share_in_speech", "numbers", "questions", "you_address"):
        rho, n = spearman([out[c][k] for c in reels], [D[c]["perf_lift"] for c in reels])
        L.append(f"| {k} | {rho} | {n} |")
    L.append(f"\n- Captions: words median {med([out[c]['caption_words'] for c in judged])}; script {dict(Counter(out[c]['caption_script'] for c in judged))}; "
             f"hashtags median {med([out[c]['caption_hashtags'] for c in judged])}; emoji median {med([out[c]['caption_emoji'] for c in judged])}")
    for k in ("caption_words", "caption_hashtags", "caption_emoji"):
        rho, n = spearman([out[c][k] for c in judged], [D[c]["perf_lift"] for c in judged])
        L.append(f"- {k} vs lift: rho {rho} (n {n})")
    for s in ("arabic", "latin", "both"):
        ps = [c for c in judged if out[c]["caption_script"] == s]
        if ps:
            L.append(f"- caption script {s}: n {len(ps)}, median lift {med([D[c]['perf_lift'] for c in ps])}")
    first = Counter(re.sub(r"\W+", " ", out[c]["caption_first_line"]).strip()[:40] for c in judged)
    L.append("- Repeated caption openings: " + "; ".join(f"'{k}' x{v}" for k, v in first.most_common(8) if v > 1 and k))
    L.append("\n## Per reel\n\n| code | date | words | w/s | latin share | numbers | questions | you | lift |\n|---|---|---|---|---|---|---|---|---|")
    for c in sorted(reels, key=lambda c: D[c]["posted"]):
        m = out[c]
        L.append(f"| {c} | {D[c]['posted'][:10]} | {m['speech_words']} | {m['words_per_second']} | {m['latin_share_in_speech']} | {m['numbers']} | "
                 f"{m['questions']} | {m['you_address']} | {D[c]['perf_lift']} |")
    (A / "script_facts.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    main()
