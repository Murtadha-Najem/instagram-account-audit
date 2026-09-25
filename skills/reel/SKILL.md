---
name: reel
description: Understand an Instagram reel, video post or photo post from its link. Use whenever the user sends an instagram.com/reel, /reels, /p or /tv link, or asks what a reel says or shows, even with no instruction beyond the link ("شوف هذا الريل", "شنو بهذا الريل", "summarise this reel", "/reel <url>"). Downloads it, reads caption, audio and video with cheap local checks first, and spends Gemini or image tokens only where they are needed.
---

# /reel

## Run
```bash
"{{PYTHON}}" "{{PROJECT_ROOT}}/reel.py" "<url>"
```
It prints the path of `bundle.md`. Add `--force-transcribe` when the on-screen captions look incomplete, `--refresh` to download again, `--max-frames N` to change the frame cap (default 8), `--dense` when something shown within one camera shot matters (a product reveal, a prop, a gesture): by default only one frame per shot is sent.

If it prints `REEL ERROR`, relay the message plainly. A cookies error means the user must export Instagram cookies (browser extension "Get cookies.txt LOCALLY", while logged in) to `~/.config/reel/cookies.txt`. Never ask them to paste cookie contents into chat.

## Read
1. Read `bundle.md` in full.
2. Read every frame listed under "Frames to read" with the Read tool. Do not open anything else in the cache folder: the pipeline already chose what is worth the tokens.
3. The Decisions section says what was skipped and why. If a skip looks wrong for this reel (for example captions clearly do not match what is said), rerun with the relevant flag rather than guessing.

## Answer
Reply in the user's language. Say what the reel is (format, who, topic), what is said, what is shown, the song if any, and whether the caption relates to the content or is just bait. Keep it proportional to the reel: a 10 second meme needs two lines.

Do not invent speech that is not in the bundle. If the speech source says "NOT transcribed", the reel has speech nobody transcribed (usually the daily free Gemini quota): say so plainly, describe only what the frames and on-screen text show, and offer to rerun it later. If speech source is "none" and the audio kind is music, the reel has no spoken content.

## Record
Write the file named on the `record file to write` line:

```markdown
---
url: <url>
account: <@account>
posted: <date>
song: <title by artist, or none>
---
# <one-line description>

<summary>

## Speech
<transcript or captions text, or none>

## On-screen text
<lines, or none>
```
