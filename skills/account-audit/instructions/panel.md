# Expert panel: an overall verdict on one dimension of the account's craft

The craft reviewers looked at the posts one batch at a time. You look across **all** of them, as one specialist, and
give the account an overall verdict on your dimension: how good it is, what it does consistently well, what it gets
consistently wrong, and what the standard should be from now on. **This verdict is apart from performance**: ignore
every lift, play and like count you come across. Another section of the report links craft to engagement.

Your role, dimensions and focus are in your task (from `taxonomy.json` "panel"). Paths are in your task.

## Read
1. `account_brief.md` and `taxonomy.json`: what kind of account this is and what good looks like for it.
2. `craft_facts.md`: score distributions and counts across all reviews (skip the performance columns).
3. `script_facts.md` when your dimensions include script, delivery or caption; the delivery table in `facts.md` when
   they include delivery.
4. Every craft JSON in `craft/` for your dimensions, and the matching sections of `craft_notes/` for the posts you
   cite. `post_index.md` gives each post's date and topic in report-language form.
5. `img/index.json`: the exhibit images already cut (file, post, good or bad, what it shows). Open the ones you plan
   to cite with the Read tool, to be sure they show what you say.

Look at a few posts yourself when a pattern needs confirming (`python look.py <code> sheet ...`), but the reviews are
your main source.

## Write `panel/<your key>.md` (report language)

```markdown
## <dimension title>

<the verdict in one paragraph: a score out of 5 with its reason, measured against accounts of this kind>

### ما يتقنه الحساب
<2 to 4 strengths that recur, each with 2 or 3 examples>

### ما يتكرر فيه الخطأ
<3 to 5 weaknesses that recur, each with how many posts show it and 2 or 3 examples, quoting the words or naming the
slide or second>

### أفضل الأمثلة وأضعفها
<the 3 best and 3 weakest posts on this dimension, one or two sentences each, with exhibits>

### المعيار المقترح
<5 to 8 concrete standards the team can hold every post to on this dimension>
```
(Headings in the report language; the ones above are Arabic.)

Every example names the post by **topic, date and ID** together, for example: ريل إطلاق المنتج الجديد
(12 أيار 2026، DXb3kQ9pLmA). Take dates and topics from `post_index.md`, never from memory.

Exhibits: a line on its own, `[[img:FILE|caption]]`, with FILE from `img/index.json`; up to three consecutive lines
sit side by side. The caption names the post (topic and date) and what the image shows. Use 3 to 6 exhibits in all.

## Rules
- Count before you generalise: "most reels" needs a number from the reviews.
- Quote the posts' own words exactly and briefly. Never reproduce song lyrics.
- No long or short dash as punctuation, no arrows, no bullet symbols inside sentences; the text is printed as written.
- Names and spellings as `account.json` and the brief give them. Never infer anyone's gender.

## Return
Two lines: your score out of 5, and the single most important standard.
