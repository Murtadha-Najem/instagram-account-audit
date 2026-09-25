---
name: repost-profile
description: Build a full, detailed Arabic PDF report on everything an Instagram account has reposted (types, timing, songs, circle, themes month by month, personality). Use when the user sends an Instagram profile link or username and asks to analyse its reposts ("حلل ريبوستات هذا الحساب", "analyse the reposts of @x", "/repost-profile <link>"). Collects the reposts through Instagram's API with the reel pipeline's cookies, runs every post through the reel pipeline, and uses a small number of subagents in two waves.
---

# /repost-profile

Everything runs from `{{PROJECT_ROOT}}` with `{{PYTHON}}` (`PY` below). Skill files are in `~/.claude/skills/repost-profile\` (`SKILL` below). The reel skill and its pipeline are used as they are: never edit `reel/`, `reel.py`, `batch.py`, `look.py` or the reel skill from here.

Output for account `<u>`: `profiles\<u>\` holds `profile.json`, `links.json`, `records\`, `coding\`, `dataset.json`, `facts.md`, `inputs\`, `sections\`, `report.pdf`.

## 0. Scope and context

- **Whose account.** Work only on a public account, or one the user can see and has a reason to analyse (their own, a public figure, someone who agreed).
- **Someone else's account.** The report stays local and uses third-person address. Say so in one line, then proceed.
- **The user's own account:**
  - Ask for, or look up in the user's own notes if they keep any, dated life events: study, graduation, jobs, moves, hobbies.
  - Write `profiles\<u>\context.md`: a short list of those facts with dates.
  - Write `profiles\<u>\context.json`: `{"utc_offset_hours": 3, "address": "second", "periods": [{"name": "<life phase>", "from": "YYYY-MM", "to": "YYYY-MM"}], "highlight_from_month": "YYYY-MM or null"}`.
- **Anyone else:** `context.json` with only `utc_offset_hours` (ask only if the region is unclear) and `"address": "third"`. Add `context.md` if the user gives facts. Automatic periods are used when none are given.

## 1. Collect (about a minute for 200 reposts)

```bash
PY SKILL/scripts/collect.py "<profile link or username>"
```

Writes `profile.json` and `links.json` (newest repost first).

**`COLLECT ERROR`: relay it plainly.**
- **Cookie errors:** the user must export Instagram cookies again to `~/.config/reel/cookies.txt` (browser extension "Get cookies.txt LOCALLY", while logged in). Never ask for cookie contents.
- **Rate limits:** stop, and suggest running again later.
- **"query did not answer as expected":** refresh the query id (see the end of this file).

## 2. Pipeline (about 13 s a post with 3 workers; cached posts reuse downloads)

Start it in the background:

```bash
PY batch.py profiles/<u>/links.json --workers 3 --run profile_<u>
```

Results go to `batch\profile_<u>\results.jsonl`. The run is resumable, and it stops by itself if Instagram refuses the cookies.

**If the run sits on one post for more than 20 minutes** (seen once, on a 22 second clip, with the workers idle):
1. Stop the background task.
2. Carry on without that post, and list it in the delivery message as not analysed.
3. It can be retried later with `reel.py` and a rerun of `batch.py`.

## 3. Watch and code (wave one): stream it while the pipeline runs

Every time roughly 25 more posts are ready (watch `results.jsonl` with Monitor), run:

```bash
PY SKILL/scripts/batches.py profiles/<u> --size 25
```

For each batch file it prints, start one background `general-purpose` agent:

> Read `SKILL/instructions/watch_and_code.md` and follow it exactly. Batch file: `<path>`.

When the pipeline has finished, run `batches.py ... --flush` for the remainder.

**Posts held back (speech Gemini could not transcribe, 429 or 503).** `batches.py` holds them and lists them. Retry each one later with:

```bash
PY reel.py "https://www.instagram.com/p/<code>/"
```

The download is cached, so only the analysis reruns. Then run `batches.py --flush` again. If the retries keep failing, hand them out with `--allow-untranscribed`: the records will say the speech is missing.

- **Checking the output:** each agent returns one line per post. Count the coding files against the links.
- **Unfinished posts:** rerun `batches.py --reassign --flush` for posts that were assigned but not finished.
- **Posts that failed in the pipeline:** report them; do not code them.
- **Lyrics rule:** if an agent's output is blocked by content filtering, a record holds lyrics. Relaunch that batch with a reminder of the lyrics rule.

This single pass replaces the old separate description and coding agents. Nothing reads the videos again after it.

## 4. Build the inputs

```bash
PY SKILL/scripts/build_inputs.py profiles/<u>
```

Writes `dataset.json`, `facts.md` and `inputs\plan.json`. It prints the writer jobs:
- one per theme group (groups under 12 posts are merged);
- one per chronology chunk of about 110 posts;
- one `numbers` job;
- one `synthesis` job.

## 5. Writers (wave two, in parallel)

For every job in `plan.json` except `synthesis`, start one background `general-purpose` agent:

> Read `SKILL/instructions/writers.md` and follow it exactly. Role: `<role>`. Section title: `<title>`. Input: `<input>`. Context file: `profiles\<u>\context.md` (skip if missing). Output: `<output>`.
> Numbers role only: add "Available charts: <charts>".

When all of them are done, start the synthesis agent:

> Role: synthesis. Inputs: `<signals.md>`, `<facts.md>`. Sections folder: `<sections_dir>`. Output: `<output>`.

## 6. PDF

```bash
PY SKILL/scripts/build_pdf.py profiles/<u>
```

It adds the introduction, the limits and an appendix of every post, then prints `report.pdf` with its page count.

**Check before sending.** Read pages 1 to 3, one chart page and one appendix page. If writing is unreadable or misplaced, fix the section markdown and rebuild.

**Deliver.** Send `report.pdf` with SendUserFile. Then give in chat, in the user's language:
- the page count;
- five or six of the most specific findings;
- the wall-clock time of each stage;
- total subagent tokens: add up the `subagent_tokens` from every task notification, by wave.

## Efficiency rules

- Two agent waves only. Wave one is about 25 posts per agent; wave two is at most 6 theme agents, plus chronology chunks, numbers and synthesis.
- The pipeline is the only thing that downloads. Never re-watch videos in wave two; open a record only when a digest is not enough.
- Scripts compute every number. Agents never count by hand what `facts.md` already has.
- Collecting, the pipeline and wave one overlap. Never wait for the whole pipeline before starting wave one.

## Refreshing the query id

Instagram occasionally changes the id of the reposts grid query.

1. In the user's logged-in Chrome (claude-in-chrome), open `https://www.instagram.com/<any account>/reposts/`.
2. Run the contents of `SKILL/scripts/capture_doc_id.js` with the JavaScript tool, then scroll the grid once with a real wheel scroll.
3. Evaluate `JSON.stringify(window.__cap)` and take the `doc_id` of `PolarisProfileRepostsTabContentRefetchQuery`.
4. Put it in `SKILL/scripts/config.json` (`reposts_doc_id`, and today's date in `reposts_doc_id_checked`).
5. Close the tab.
