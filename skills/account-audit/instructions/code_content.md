# Watch and code a batch of posts (content and engagement pass)

You code each post in your batch so that later stages can explain **what this account posts, and what people respond
to**. Nothing reads the videos after the two review passes, so everything needed must be in your two files.

## First, the account
Read `account_brief.md` and `taxonomy.json` (paths in your task). They say what kind of account this is and give the
topics, formats, custom fields and comment categories you must use. Judge every post as a post of *this* account.

## The batch
A JSON list. Each entry has: `shortcode`, `type`, `bundle` (path to `bundle.md`), `people` (who the face recogniser
found and in how many frames; P numbers are recurring people nobody has named), `comments` (with ids), `delivery`
(how the speech sounds, heard by an audio model, or null), `extra_transcripts` (other video slides of a carousel, or
null), `record` and `coding` (the two paths you write).

Commands run from the project folder given in your task, with the Python given there:
- `python look.py <shortcode> sheet --start S --end E --n N`: contact sheet of N moments (up to 24); prints the image path.
- `python look.py <shortcode> frame SECONDS`: one full frame, for reading text.
Open every printed image with the Read tool.

## Understand each post
1. Read `bundle.md` in full (caption, metadata, audio, speech, on-screen text, timeline). Ignore its "record file to
   write" line.
2. Photos and carousels: read every image listed under "Frames to read". The slides are the content.
3. Videos: open an overview sheet (`--n 12` to `16`) and **always a dense sheet of the first 3 seconds**
   (`--start 0 --end 3 --n 6`); the hook is coded from it. Open more only where the content is unclear.
4. The bundle shows plays and likes. **Do not let them colour any judgement.** Code what the post is, not how it did.

## People
Use the names in `account.json` and the brief. Anyone unnamed: by role (host, guest, the artist, a customer) or by
the name the post itself gives. P numbers stay P numbers. Never infer anyone's gender from a name, a handle or a face;
use the pronoun `account.json` gives, or none.

## Write the record (Markdown, in the report language)

```markdown
---
shortcode: <code>
type: <reel | carousel | photo>
posted: <date>
length: <N s video | N slides>
people: [<names or P numbers on screen>]
---
# <one-line description>

## What it is
<what happens, in order: who speaks, about what, what is shown, what the slides say>

## Opening
<exactly what the viewer sees and hears in the first 3 seconds: first spoken line verbatim, first on-screen text
verbatim, first image>

## Speech
<transcript verbatim from the bundle, or none>

## On-screen text and slides
<every distinct line or slide text, in order, or none>

## Caption
<caption verbatim>

## Comments
<one line per comment: id, text, your category>
```
(Headings may be in the report language.)

## Write the coding (JSON, UTF-8)

```json
{
  "shortcode": "…",
  "digest": "70 to 120 words in the report language: what the post says and shows, who is in it, the main claim, the call to action, anything distinctive in how it is made",
  "quotes": ["0 to 4 short exact quotes (under 15 words) from speech, screen or caption"],
  "topic": "one key from taxonomy topics",
  "topics": ["1 to 3 keys from taxonomy topics, main first"],
  "format": "one key from taxonomy formats",
  "custom": {"<each custom field name>": "value as the taxonomy defines it"},
  "presenter": "who carries the post: a name, a P number, or host | guest | voiceover_only | none",
  "speakers": ["everyone who speaks, by name, P number or role"],
  "language": "the spoken language and dialect, e.g. iraqi_arabic | msa | english | mixed_arabic_english | no_speech",
  "text_language": "arabic | english | both | other | none (on-screen and slide text)",
  "register": "casual | semi_formal | formal | none",
  "hook": {"first_line": "verbatim", "type": "one of HOOK_TYPES", "seconds_to_point": 0, "strength": 1, "note": "one sentence: would this stop someone scrolling, and why"},
  "structure": "one of STRUCTURES",
  "numbers_cited": 0,
  "subtitles": "none | full | partial",
  "text_density": "none | low | medium | high",
  "production": "one of PRODUCTION",
  "setting": "office | outdoor | studio | event_venue | home | shop | stage | car | graphic_only | mixed | other",
  "music": "none | background | trending_audio | dominant | original_music",
  "cta": ["0 to 3 of CTAS"],
  "value_to_viewer": "one of VALUE",
  "audience_target": "who the post speaks to, in two to four English words",
  "tone": ["1 to 3 of TONES"],
  "clarity": 1,
  "energy": 1,
  "speaking_style": {"applies": true, "pace": "slow | medium | fast", "delivery": "scripted_reading | natural_conversational | interview_answer | presentation | performance",
                      "eye_contact": "camera | off_camera | mixed | none", "fillers": "none | few | many", "notes": "one or two sentences"},
  "strengths": "one sentence: the strongest thing about this post for this account's goal",
  "weaknesses": "one sentence: the weakest thing, concretely",
  "comments_coded": [{"id": "…", "category": "one of COMMENT_CATS or a taxonomy extra", "sentiment": "positive | neutral | negative"}],
  "keywords": ["3 to 6 short English keywords"],
  "looked_at": "which sheets and frames you opened"
}
```

`hook.strength`, `clarity` and `energy` are integers 1 to 5. `seconds_to_point` is the second the main point starts.
Photos and carousels: `hook` is the first slide, `seconds_to_point` 0, `speaking_style.applies` false with the other
style fields null. Use `delivery` (heard audio) for pace and fillers when it is there.

HOOK_TYPES: question, bold_claim, statistic, problem_pain, story, direct_address, curiosity_gap, title_card,
visual_surprise, news_headline, humor_setup, trend_sound, reaction, performance_start, product_reveal, slow_intro_no_hook

STRUCTURES: problem_solution, list_points, story, qa_interview, single_fact, argument_evidence, announcement,
highlights_montage, tutorial_steps, skit, performance, before_after, reaction, other

PRODUCTION: phone_selfie, phone_filmed_by_other, studio_multi_cam, professional_edit, template_design, event_camera,
screen_recording, ugc_repost, mixed

CTAS: link_in_bio, visit_website, download, buy, shop_link, contact, dm, follow, comment, share_save, register_event,
apply_job, stream_listen, watch_full, vote, none

VALUE: insight, practical_tip, news, entertainment_humor, emotion_inspiration, art_performance, behind_the_scenes,
product_showcase, promotion, community, recruitment, personal_life

TONES: informative, serious, confident, friendly, playful, humorous, urgent, inspiring, celebratory, formal,
promotional, critical, emotional, provocative

COMMENT_CATS: praise_congrats, fan_love, emoji_only, question_about_content, request_link_or_info, price_question,
purchase_intent, business_inquiry, job_inquiry, tag_friend, agreement_opinion, disagreement_critique, personal_story,
spam_promo, account_reply, other

## Rules
- Quote speech, screen text and captions in their original language. Describe only what the bundle and images show;
  never invent speech. When OCR and the image disagree, trust the image.
- Never reproduce song lyrics: name the song, quote at most four words.
- Be decisive with fixed values; pick the closest rather than `other`.
- Code every comment (a reply by the account itself is `account_reply`). A post with hundreds: code them all briefly.
- Overwrite files that exist. After each post, check the coding file parses as JSON.

## Return
One line per post and nothing else: `<shortcode> | ok or failed: reason | <one-liner in the report language>`
