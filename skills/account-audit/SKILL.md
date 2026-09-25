---
name: account-audit
description: Full audit of any Instagram account from its link or handle, of any kind (company, brand, shop, creator, artist, memes, news, public figure) and any size. Collects every post, reel, carousel, comment, liker, tagged post, partner and highlight, recognises the people on screen, then produces a PDF report in two linked halves - what the audience engages with and why, and an expert review of the content craft (script, wording, delivery, filming, editing, design, caption) apart from engagement - plus before and after rewrites and a playbook. Use when the user asks to analyse, audit or evaluate an Instagram account or page ("حلل حساب", "سوي تقرير عن هذا الحساب", "audit @x", "/account-audit <link>"). Not for a single reel (use /reel) or for an account's reposts (use /repost-profile).
---

# /account-audit

Everything runs from the project folder in `scripts/config.json` (`project_root`) with its Python (`PY` below).
Skill files: `~/.claude/skills/account-audit\` (`SKILL` below). Scripts run from `SKILL\scripts`.
Output for account `<u>`: `profiles\<u>\audit\`. The reel pipeline is used as it is: never edit `reel/`, `reel.py`,
`batch.py`, `look.py` or the reel skill from here.

**Speak the user's language** in every message: questions, the cost table, progress, delivery. The report is in the
user's language unless they ask otherwise (`report_language` in `account.json`).

**The standard for every finding:** it rests on posts you or the agents actually looked at, cites them by topic, date
and ID, and never borrows general social-media advice that this account's posts do not show.

## 0. Ready check and the reel skill

```bash
PY SKILL/scripts/preflight.py
```

- **The reel skill is required.** If preflight says it is missing, ask the user to install `/reel` first, and stop.
- **Other missing pieces:** relay the fix the script prints. Face models missing only means stage 4 is skipped.
- **Cookies:** never ask the user to paste cookie contents. They export them with the browser extension
  "Get cookies.txt LOCALLY" while logged in.

## 1. First look (a handful of requests, before anything is approved)

```bash
PY SKILL/scripts/recon.py "<link or handle>"
```

Read `audit/recon/recon.md` and look at `audit/recon/sheet.jpg`. From them, tell the user in a few lines:
- what the account seems to be (type, language, what it posts);
- its size;
- how many posts fall in the window (default: the last 12 months).

The full understanding comes later, in stage 5, from a real sample.

**Private accounts:** only what the login can see. **Someone else's account:** fine when it is public. The report
stays with the user.

## 2. Ask, then show the cost, then wait

Ask in **one message**. Everything is optional: the audit runs from nothing, but each answer improves it. Ask only
what applies:

1. **Window:** the last 12 months, or another range?
2. **Whose account:** the user's own, a client's, or a third party's?
   - **If it is theirs or a client's and a business account:** ask for the owner's data
     (`references/owner_data.md`: the Meta Business Suite export, boosted posts, audience and reel screenshots).
     Say it is the most useful single addition.
3. **Group accounts:** the account's own other accounts (a sister brand, a magazine, the founder's page), so posting
   with them is not counted as a partnership.
4. **Team and faces:** who works on the account, with their Instagram handles and one or two posts where each
   person clearly appears. This names the faces and separates team likes from the audience. Without it, recurring
   faces become "person 1, 2 ..." and team likes are found by behaviour alone.
5. **Brand:** colours and a logo for the report, if they want the account's own look.
6. **Anything else** the posts cannot show: goals, campaigns, known events.
7. **Large accounts only** (recon `size_class` large or huge):
   - Collection is never reduced. It runs at the slow pace, and takes longer.
   - Recommend a **spare Instagram login** for collecting, so the user's main account carries no risk. Its cookies go
     in a separate file, passed with `--cookies`.
   - Offer review of all posts, or of a stratified sample, with the cost of each (`modes_sampled_150` in recon.json).

**Then show the modes as a table, with this account's numbers from `recon.json`:**
- the time each takes, and how long collection alone takes;
- the approximate tokens each uses;
- a one-line "what you get" for each.

| mode | what you get |
|---|---|
| full | both halves, the link between them, rewrites, errors, playbook, appendix |
| engagement | what the audience responds to, who engages (genuine against internal), timing, partners: no craft review |
| content | the expert craft review of every post and the panel verdicts, apart from the numbers: no likers or comments collection |
| brief | engagement on every post, craft review on 20 to 25 posts, about six pages |

State the assumptions in one line: the estimate scales with post count and type mix, and Gemini free keys are used
for audio. **Do not start until the user picks a mode and says go.** Write what they said to `audit/account.json`:

```json
{"username": "", "mode": "full", "since": "YYYY-MM-DD", "report_language": "ar", "relationship": "own | client | third_party",
 "utc_offset_hours": 3, "group_accounts": [], "display_name": "",
 "team": [{"name": "", "display": "name as written in the report language", "handles": [], "reference_posts": [], "pronoun": null}],
 "face_names": {}, "brand": {"colors": {}, "logo_light": null, "logo_dark": null},
 "cookies": null, "pace": "normal | slow", "house_style_no_dashes": true, "notes": ""}
```

- **Pronouns:** only as the user gives them. Never infer one from a name.
- **Names:** spelled exactly as the user writes them.

## 3. Collect (background, resumable; slow pace for large accounts)

```bash
PY SKILL/scripts/collect.py posts <u> [--since YYYY-MM-DD] [--cookies PATH] [--pace slow]
```

Then start the rest in the background, as one command, while stage 4 runs. The layers depend on the mode:
- **full, engagement, brief:** comments, likers, tagged, partners, highlights, slides.
- **content:** highlights and slides only.

```bash
PY SKILL/scripts/collect.py <layer> <u>
```

**`COLLECT ERROR`: relay it plainly.**
- **Cookies expired:** the user exports them again.
- **Rate limit:** stop and resume later; nothing collected is lost.
- **Query ids changed:** run `PY SKILL/scripts/capture_doc_ids.py`, then retry.
- **403 or a restricted login:** stop at once and tell the user. Never push on.

## 4. Pipeline, profiler sample, faces, delivery

1. `PY SKILL/scripts/batches.py <u> sample`, then run the pipeline on the sample first:
   `PY SKILL/scripts/run_pipeline.py <u> --codes <audit>/profile_sample.txt`.
2. Then the full pipeline in the background: `PY SKILL/scripts/run_pipeline.py <u>`. It is resumable, uses the
   account's cookies and pace, and stops by itself if Instagram refuses.
3. Faces run alongside it, unless the face models are missing:
   - `faces.py <u> extract`, repeated as posts finish (a loop every few minutes is fine);
   - `faces.py <u> register` when the user gave reference posts.
4. After the pipeline, run these:
   - `faces.py <u> extract`, then `faces.py <u> unknowns`;
   - **show the user `faces/unknowns.jpg`** and ask who the recurring people are (optional; unnamed stay numbered);
   - put the names in `face_names` in account.json;
   - `faces.py <u> match`.
5. `PY SKILL/scripts/delivery.py <u>` after the pipeline (Gemini listens to every video with speech).
6. `PY SKILL/scripts/owner_data.py <u>` if the owner sent files.

**Posts the pipeline could not transcribe** (Gemini 429 or 503):
- Retry them later with `PY reel.py "https://www.instagram.com/p/<code>/"`. The download is cached, so only the
  analysis reruns.
- `batches.py` holds them back until they are transcribed, or until you pass `--allow-untranscribed`.

## 5. Understand the account (one agent, before any coding)

As soon as the sample is through the pipeline, start one `general-purpose` agent:

> Read `SKILL/instructions/profile.md` and follow it exactly. Account folder: `<audit>`. Report language: `<lang>`.
> Write `<audit>/analysis/account_brief.md` and `<audit>/analysis/taxonomy.json`.

Read both files yourself. If the brief contradicts what you saw or what the user said, fix it before stage 6.

If it lists questions for the user that would change the analysis, ask them now in one message. Carry on without an
answer if the user does not reply.

## 6. Two review waves (agents, streamed while the pipeline runs)

The wave depends on the mode:
- **Content wave:** full, engagement and brief.
- **Craft wave:** full, content and brief.

**Starting batches.** Every time more posts are ready, run:
- `PY SKILL/scripts/batches.py <u> content` for the content wave;
- `PY SKILL/scripts/batches.py <u> craft [--sample 25 | --basics]` for the craft wave.

Then run the same command with `--flush` once the pipeline is done.

- **brief mode:** `--sample 25`.
- **content mode:** `--basics`, because there is no content wave.
- **Sampled large accounts:** `--sample N`.

The craft wave for a post starts after its content coding exists, except in content mode.

**One background `general-purpose` agent per batch file:**

> Read `SKILL/instructions/code_content.md` (or `code_craft.md`) and follow it exactly. Batch file: `<path>`.
> Account brief: `<audit>/analysis/account_brief.md`. Taxonomy: `<audit>/analysis/taxonomy.json`.
> Account: `<audit>/account.json`. Project folder: `<project_root>`. Python: `<python>`. Report language: `<lang>`.

**Checking the waves:**
- Count the output files against the batch.
- `--reassign` hands out again posts that were assigned but never finished.
- If an agent's output is blocked by content filtering, a transcript holds lyrics: relaunch that batch with a reminder
  of the lyrics rule.

## 7. Numbers (scripts only)

```bash
PY SKILL/scripts/build_dataset.py <u>
PY SKILL/scripts/genuine.py <u>          # not in content mode
PY SKILL/scripts/script_metrics.py <u>
PY SKILL/scripts/craft_facts.py <u>      # not in engagement mode
PY SKILL/scripts/images.py <u>           # exhibits named by the craft reviewers
PY SKILL/scripts/appendix.py <u>         # also writes post_index.md
```

Rerun `build_dataset.py` after `genuine.py` only if you changed account.json. Read `facts.md`, `genuine_facts.md`,
`script_facts.md` and `craft_facts.md` yourself before briefing the writers, so you can catch anything odd.

## 8. Expert panel, then writers (agents, in parallel where they can be)

**Panel (full, content and brief):** one background agent per entry of `taxonomy.json` "panel":

> Read `SKILL/instructions/panel.md` and follow it exactly. Your key: `<key>`. Role: `<expert>`.
> Dimensions: `<dimensions>`. Focus: `<focus>`. Account folder: `<audit>`. Project folder and Python: `<...>`.
> Report language: `<lang>`. Write `<audit>/analysis/panel/<key>.md`.

- **brief mode:** ask for half the length.
- **Placing the verdicts:** copy each panel file into `sections/` as `07_<key>.md` to `10_<key>.md`, in the order the
  taxonomy lists them.

**Writers:** one background agent per role in `instructions/write_report.md` that the mode needs. The synthesis role
goes last, after all the others have finished.

> Read `SKILL/instructions/write_report.md` and follow it exactly. Role: `<role>`. Mode: `<mode>`.
> Account folder: `<audit>`. Report language: `<lang>`. Write into `<audit>/analysis/sections/`.

## 9. Build, check, fix, deliver

```bash
PY SKILL/scripts/build_report.py <u>
```

**The build must print `CHECK: clean`.** Otherwise fix the section files and rebuild. The check covers:
- a heading left at a page bottom;
- dashes or arrows;
- a post cited without its date;
- an ID that is not in the dataset;
- missing charts or images.

**Tables and paragraphs never split across pages.** The stylesheet already prevents it.

**Then read it yourself:**
- the cover, the contents page and the summary;
- one engagement page and one craft page with images;
- one rewrites page and the playbook.

Check that every number you see is in a facts file, and that names are spelled as the user gave them.

**Deliver:**
- Send `report.pdf` with SendUserFile.
- Then, in the user's language, give:
  - the page count;
  - the five or six most specific findings;
  - the wall-clock time of each stage;
  - the subagent tokens by wave, from the task notifications, against the estimate you gave in stage 2.

If the numbers differ a lot, correct `cost_per_post` in `config.json` so the next estimate is closer.

## Efficiency rules

- **Scripts count; agents judge.** No agent computes a number a script has.
- **Only two waves watch the posts.** The panel and the writers read text and the cut exhibits, not videos.
- **Stages overlap.** Collecting the other layers, the pipeline, faces and both waves run together. Never wait for the
  whole pipeline before starting a wave.
- **Batches of about 35 weight units, at most 10 agents per wave.**
- **One download per post:** the pipeline's cache serves every later look.
- **Normal-sized accounts** (like a company page with a few hundred posts) need none of the large-account handling:
  normal pace, all posts reviewed.

## Updating an earlier audit

Run collect again with a new `--since`. The pipeline, the faces and the waves skip what is done.

**For a comparison with an earlier audit:** keep the old `analysis/` folder under a dated name. Then add a section
that compares the old facts files with the new ones.
