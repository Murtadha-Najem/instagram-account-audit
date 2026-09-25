# Watch and code one batch of reposts

You receive a batch file (JSON list). Each entry is one Instagram post that someone reposted to their profile: its `bundle` (output of a local pipeline that downloaded the post, read its metadata, classified the audio, transcribed speech or sung lyrics where needed, and read on-screen text), the `record` path to write, the `coding` path to write, and the reposter's own `repost_note` if any.

For every post you do three things in one pass: understand it by looking, write its record, write its coding. Nothing else reads the video after you, so everything later stages need must be in these two files.

Commands run from `{{PROJECT_ROOT}}` with `{{PYTHON}}`:
- `python look.py <shortcode> sheet --start S --end E --n N`: contact sheet of N evenly spaced moments (N up to 24). Prints the image path and each cell's time.
- `python look.py <shortcode> frame SECONDS`: one full-resolution frame, for reading text.
Open every printed image with the Read tool.

## Understand each post

1. Read the `bundle.md` in full. Ignore its "record file to write" line: write to the paths in the batch file.
2. Photo posts: read the images under "Frames to read".
3. Videos: open the overview sheet first. With the caption, audio, speech and timeline, decide what the post needs:
   - picture barely matters or barely changes: stop, the overview is enough;
   - meaning is in the motion or sequence (a gag, a reaction, a process): open a dense sheet over where it happens;
   - text changes on screen (lyrics, a list, slides): make sure every distinct line is read, with full frames where a sheet is too small;
   - the timeline hints at something the overview misses: look there.
   Compare distant moments, not only neighbouring ones. Stop as soon as you understand it.

## Write the record (Arabic)

```markdown
---
url: <url>
account: "@<account>"
owner_name: "<name>"
posted: <date>
format: <video Ns | photo post, N images>
plays: <number or omit>
likes: <number, omit when hidden>
comments: <number>
reposts: <number or omit>
location: <name or omit>
song: <title by artist (source), or none>
speech_language: <language, or none>
hashtags: [<tags>]
repost_note: "<note text or empty>"
repost_note_at: <UTC time or omit>
looked_at: <overview only | sheets and frames opened>
---
# <one-line description in Arabic>

## الوصف
<what the post is, what happens in order, what is said or sung, tone and purpose, why it is funny or meaningful>

## الكلام
<transcript verbatim, or "لا يوجد">

## النص على الشاشة
<every distinct line as it appears, or "لا يوجد">

## الكابشن
<caption verbatim, then one line: relates to the content or bait>

## ملاحظات
<anything notable from the metadata>
```

## Write the coding (JSON, one object, UTF-8, ensure_ascii off)

```json
{
  "shortcode": "…",
  "digest_ar": "60 to 110 Arabic words that let someone who never saw the post write about it precisely: the scene and people, the exact on-screen text or its gist, what is said, the song and what it is about, the joke or point, and anything odd about the caption",
  "quotes": ["0 to 4 short exact quotes from on-screen text, speech or caption, each under 15 words, never song lyrics or lines of a modern poem"],
  "primary_theme": "one value from THEMES",
  "themes": ["1 to 4 values from THEMES, primary first"],
  "form": "one value from FORMS",
  "language": "one value from LANGUAGES: the content's own language or dialect, not the caption's",
  "cultural_frame": "iraqi | arab_other | western | east_asian | south_asian | global_neutral",
  "tone": ["1 to 3 values from TONES"],
  "emotion": "one value from EMOTIONS",
  "intensity": 1,
  "humor_type": "none | absurd | relatable_observational | irony_sarcasm | wordplay | dark | wholesome | cringe_awkward | slapstick_physical | nerd_inside_joke",
  "stance_ar": "what the post asserts, a few Arabic words",
  "values": ["0 to 3 values from VALUES"],
  "self_reference": "identity | mood_now | message_to_someone | shared_joke | admiration | aspiration | information_share | pride_belonging | none",
  "relationship_target": "none | romantic_partner_or_crush | lost_love | friends | family | colleagues_peers | society_general | self",
  "people_featured": "none | self_creator_talking | ordinary_people | celebrity_or_public_figure | friends_or_classmates | children | animals_only | fictional_characters",
  "signal_ar": "one Arabic sentence: the most specific thing this repost suggests about the reposter's tastes, mood or situation, naming the evidence; say ضعيف when it is plain entertainment",
  "signal_strength": 1,
  "specifics": {"artist": null, "work": null, "place": null, "topic_keywords": ["3 to 6 short English keywords"]},
  "caption_bait": false,
  "looked_at": "overview only | the sheets and frames opened"
}
```

`intensity` and `signal_strength` are integers 1 to 5. The reposter's own note, when present, is the strongest evidence of why they reposted: use it in `signal_ar`.

THEMES: romance_longing, heartbreak_loss, loneliness_isolation, friendship_loyalty, family_parents, betrayal_trust, self_worth_boundaries, stoicism_patience, motivation_ambition, career_job_hunt, study_university, graduation_milestone, programming_software, ai_tools, tech_general, data_science_math, work_office_life, money_economy, local_daily_life, society_critique, arab_culture_heritage, nostalgia_childhood, classical_poetry, modern_poetry_prose, music_song_appreciation, religion_spirituality, philosophy_existential, mental_health_mood, humor_absurd, humor_relatable, animals_cats, animals_other, food, travel_places, nature_scenery, art_design_craft, film_tv_anime, gaming, chess, sports_football, science_curiosity, history, politics_news, social_media_meta, gender_relationships_dynamics, marriage_dating_culture, health_fitness, fashion_beauty, cars_vehicles, parenting_children, language_linguistics, life_lessons_wisdom, kindness_humanity, other

FORMS: text_meme_image, screenshot_tweet_or_post, quote_card, photo_carousel, skit_acted, talking_head, street_or_candid_clip, song_clip_with_visuals, lyrics_on_screen, poetry_recitation, edit_montage_aesthetic, film_tv_clip, animal_clip, tutorial_or_explainer, news_or_announcement, event_or_ceremony_footage, ai_generated_video, gameplay_or_screen_recording, other

LANGUAGES: iraqi_arabic, gulf_arabic, egyptian_arabic, levantine_arabic, maghrebi_arabic, other_arabic_dialect, msa_classical, english, mixed_arabic_english, other_language, no_language

TONES: funny, sad, tender, melancholic, nostalgic, hopeful, inspiring, bitter, angry, sarcastic, calm, awe, cute, proud, anxious, romantic, reflective, cynical, playful, serious

EMOTIONS: joy_amusement, sadness, longing, love_tenderness, pride, calm_peace, anxiety_stress, anger_frustration, awe_wonder, hope, bitterness_disillusion, embarrassment, comfort, curiosity, neutral

VALUES: loyalty, sincerity_authenticity, patience, dignity_self_respect, ambition, knowledge, hard_work, independence, kindness, faith, family, humility, freedom, justice, beauty, simplicity, competence, humor, belonging

## Rules

- **Never reproduce song lyrics** from the audio, the screen or the web, in the record or the coding. Name the song and artist, say what it is about and how the post uses it, quote at most a fragment of four words, and write "كلمات أغنية: <title> لـ <artist>، غير منسوخة" in the speech and on-screen sections. The same for long modern poems. Classical poetry (pre-modern poets) may be quoted one verse at a time. Do not search the web for lyrics.
- Quote other speech, captions and on-screen text in the original language. Describe only what the bundle and images support; never invent speech. When OCR and the image disagree, trust the image.
- Never infer anyone's gender from a name or handle; refer to accounts by handle.
- Code from the content. Inference about the reposter belongs only in `signal_ar`.
- Be decisive with the fixed values; pick the closest one rather than `other`.
- Overwrite files that already exist. After each post, check the coding file parses as JSON.

## Return

One line per post and nothing else: `<shortcode> | ok or failed: reason | looked at: … | <Arabic one-liner>`
