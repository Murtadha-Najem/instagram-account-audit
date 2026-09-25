"""Listen to how people speak: Gemini hears the audio of every video post with speech and rates the delivery, which the
reviewing agents cannot do from a transcript (voice, energy, pace, pauses, fillers, sound quality, music balance).

usage: python delivery.py <username> [--workers 3]
reads the pipeline's video for every post whose bundle has speech; writes audit/delivery/<code>.json; resumable.
Uses the reel pipeline's Gemini keys and model. Short audio: roughly 2,000 tokens a minute.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from common import CACHE, PROJECT, root, username_from

sys.path.insert(0, str(PROJECT))
from reel.common import run_bytes  # noqa: E402
from reel.speech import MODEL, _skill  # noqa: E402

PROMPT = """You are a presentation and voice coach reviewing a short social media video. Listen to the audio only.
Judge how the speech is delivered, not what it says. Be specific and honest; most videos are average (3).
If several people speak, describe the main speaker and note the others briefly.
Return JSON with:
- speakers: number of distinct voices
- main_speaker_share: share of speech time by the main speaker, 0 to 1
- pace: slow | medium | fast
- energy, clarity, confidence, warmth, vocal_variety, audio_quality: integers 1 to 5
- pauses: rushed | natural | too_many
- fillers: none | few | many, with filler_examples: up to 5 filler words heard, as spoken
- music: none | background_balanced | music_too_loud | music_only
- noise: none | light | distracting (room echo, street, hum, wind)
- first_seconds: one sentence on how the first 3 seconds are delivered
- strengths: up to 3 short phrases
- problems: up to 3 short phrases, each with the second it happens if clear
- notes: two sentences of coaching advice
Never transcribe song lyrics."""
SCHEMA = {"type": "object", "properties": {
    "speakers": {"type": "integer"}, "main_speaker_share": {"type": "number"},
    "pace": {"type": "string"}, "energy": {"type": "integer"}, "clarity": {"type": "integer"},
    "confidence": {"type": "integer"}, "warmth": {"type": "integer"}, "vocal_variety": {"type": "integer"},
    "audio_quality": {"type": "integer"}, "pauses": {"type": "string"}, "fillers": {"type": "string"},
    "filler_examples": {"type": "array", "items": {"type": "string"}}, "music": {"type": "string"},
    "noise": {"type": "string"}, "first_seconds": {"type": "string"},
    "strengths": {"type": "array", "items": {"type": "string"}}, "problems": {"type": "array", "items": {"type": "string"}},
    "notes": {"type": "string"}}, "required": ["pace", "energy", "clarity", "confidence", "audio_quality", "notes"]}


def has_speech(code):
    f = CACHE / code / "bundle.json"
    if not f.exists() or not (CACHE / code / "video.mp4").exists():
        return False
    b = json.loads(f.read_text(encoding="utf-8"))
    sp = b.get("speech") if isinstance(b.get("speech"), dict) else {}
    return bool(sp.get("segments")) or "speech" in str((b.get("audio") or {}).get("kind", ""))


def listen(code, skill, out):
    from google.genai import errors, types
    audio = run_bytes(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(CACHE / code / "video.mp4"), "-vn",
                       "-ac", "1", "-ar", "16000", "-b:a", "32k", "-f", "mp3", "-"])
    rotator = skill.KeyRotator()
    config = {"temperature": 0.2, "max_output_tokens": 2048, "response_mime_type": "application/json", "response_schema": SCHEMA}
    for attempt in range(6):
        try:
            resp = rotator.client().models.generate_content(
                model=MODEL, contents=[PROMPT, types.Part.from_bytes(data=audio, mime_type="audio/mp3")], config=config)
            data = json.loads(resp.text or "{}")
            (out / f"{code}.json").write_text(json.dumps({"shortcode": code, **data}, ensure_ascii=False, indent=1), encoding="utf-8")
            return f"{code} ok"
        except errors.APIError as e:
            if e.code == 429 and "PerDay" in str(e) and not rotator.rotate():
                return f"{code} failed: daily Gemini quota used up"
            if e.code in skill.ROTATE_ON:
                rotator.rotate()
            time.sleep(8 * (attempt + 1))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return f"{code} failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="only the first N (a test)")
    args = ap.parse_args()
    user = username_from(args.profile)
    R = root(user)
    out = R / "delivery"
    out.mkdir(exist_ok=True)
    codes = [l["shortcode"] for l in json.loads((R / "links.json").read_text(encoding="utf-8"))]
    todo = [c for c in codes if not (out / f"{c}.json").exists() and has_speech(c)]
    todo = todo[:args.limit] if args.limit else todo
    print(f"delivery: {len(todo)} posts with speech to hear", flush=True)
    skill = _skill()
    with ThreadPoolExecutor(args.workers) as pool:
        for msg in pool.map(lambda c: listen(c, skill, out), todo):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
