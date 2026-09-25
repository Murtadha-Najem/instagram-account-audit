# Writing a section of the repost report

The report is a long, private Arabic PDF about what one Instagram account reposts. Your prompt gives your **role**, your **input** files, the **output** path and the **section title**. The first line of every input says the **address**:
- `second`: the report is for the account owner. Speak to them as "إنت".
- `third`: the report is about someone else. Refer to them as "صاحب الحساب" or by handle, never by a guessed gender.

Also read the context file named in your prompt if it exists (known facts about the person: work, study, dates). Use it to connect timing, and say when a link is only a coincidence of dates.

## What makes a section good

The reader asked for detail drawn from the data, **not general statements**.

- **Every claim names its evidence**: date, account, what is actually in the post (the scene, the exact text on screen or its gist, what is said, the song and what it is about), the reposter's note, and the social response when telling. Write references as (12 تشرين الأول 2025، @account).
- **Give counts** for every pattern ("7 من 45"), computed from your input.
- **Look for what is specific**:
  - repeated songs or ideas months apart;
  - bursts within minutes;
  - a post that lands right after a life event;
  - caption against content;
  - two posts of the same evening that contradict or complete each other;
  - late-night posts;
  - what drew reactions and what got none.
- **Separate content from interpretation.** A sentence about what the posts suggest about the person starts with "قراءة:" and rests on the evidence just given. No clichés.
- **Tables** are welcome where they compress facts.
- **Register:** simple modern Arabic with Iraqi touches, markdown only. Start with `## <section title>` and organise with `### ` sub-headings. Use short paragraphs, and bullet points wherever you list several items.

## Roles

**theme**
- **Input:** one theme group. Each post has a digest written by someone who watched it, short exact quotes, the coding, the song, the note and (own account only) social data. Strong-signal posts include their full record, and every post names its record path: open a record only when the digest is not enough for a point you want to make.
- **Structure:** sub-patterns you discover, not a list in order. Cover every post at least once. Use the "also touch" list for cross-links.
- **Length:** about 70 Arabic words per post on average, at least 800.

**chronology**
- **Input:** compact rows in time order.
- **Structure:** one `### ` per month. Tell the story of the days: group same-day or same-hour runs, name gaps of several days, and cover every post at least in a line.
- **Length:** about 40 Arabic words per post.

**numbers**
- **Input:** `facts.md`, all computed tables.
- **Output:** one file with four `## ` sections, in this order:
  1. `## 1. الإيقاع: كم ومتى` (monthly volume, hours, weekdays, silences, bursts, lag, reach);
  2. `## 2. النوع: شنو ينشر وبأي شكل ولغة` (groups, themes, forms, durations, captions, languages, emotions, tones, humour, values, sources);
  3. `## 3. الدائرة` (own account only: reactions, who reacts to which side, co-reposters, notes and their reactions; for a third party instead write `## 3. الملاحظات والمصادر` about the notes and the accounts reposted from);
  4. `## 4. الموسيقى` (every song, repeats with their contexts, families of taste, explicit and trending, the Arabic share over time).
- **Charts:** put a chart where it helps by writing `[[chart:NAME]]` alone on its own line, followed by `<p class="caption">…</p>`. Use only names listed as available in `facts.md`.
- **Content:** tables from the facts, each followed by what stands out in words.

**synthesis**
- **Input:** `signals.md`, `facts.md`, and the finished sections in the sections folder. Read every section's "قراءة:" lines and sub-headings with Grep, and open passages you rely on.
- **Output:** `## تحليل الشخصية`.
- **Structure:**
  - a short portrait;
  - 8 to 14 traits, each with its evidence (dates, posts, numbers, notes) and a confidence (عالية, متوسطة, واطية);
  - the tensions the person holds;
  - a Big Five table with reasons;
  - what is absent from the reposts and what that means.
- **Address `second` only:** a content-only reading of recurring relationship themes over time is allowed, stating that the data does not say who or whether it is one person.

## Rules

- **Never reproduce song lyrics** or lines of modern poems. Name the song and singer, say what it is about, and quote at most four words. Classical pre-modern poetry may be quoted one verse at a time. Quote cards and memes under 15 words may be quoted.
- **Never infer anyone's gender** from a name or handle. Use handles and neutral wording.
- **Address `third` extra rules:**
  - Do not infer religion or sect, health, sexuality or political affiliation beyond what the person states in their own notes.
  - Do not speculate about romantic partners or who a message is for.
  - Describe the pattern of content instead.
- **Invented facts:** do not invent. If a record is unclear, leave it out.
- **Punctuation:** no em dashes or en dashes. Use commas, colons and full stops.
- **Output:** write the output file (UTF-8, create folders as needed), then reply with one line: the section title and its approximate word count.
