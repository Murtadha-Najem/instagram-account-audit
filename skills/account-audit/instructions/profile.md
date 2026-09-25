# Understand the account before anyone codes it

Every later judgement depends on knowing what this account is. A company page, an artist, a meme page, a news outlet,
a shop, a creator's personal page, a charity and a politician's office are judged by different standards: what they
post, who they talk to, what counts as success, and what "good craft" means for them. You work that out from the posts
themselves, then write the brief and the coding scheme every other agent uses.

## Read
Paths are given in your task:
1. `account.json`: what the user told us (may be nearly empty; never contradict it).
2. `profile.json`: name, bio, followers, following, post count.
3. `recon/recon.md` and `recon/sheet.jpg`: the latest posts with captions and numbers, and their covers.
4. `profile_sample.json`: a spread of about 20 posts (types, the whole window, strongest and weakest). For each one,
   read its `bundle.md` in full and read the frames it lists with the Read tool. Carousels: read every slide listed.
5. `owner_data.md` if it exists (the owner's own export).

Look, do not assume. If the bio says "research firm" but the posts are mostly memes, the posts win and you say so.

## Write `account_brief.md` (in the report language given in your task; the headings below are the Arabic ones, translate them for another language)

```markdown
# <account name> (@handle)

## ما هو الحساب
<what kind of account this is, in one paragraph; who is behind it (a company, a person, a team), the market or
scene it belongs to, and the evidence for each claim (bio line, recurring faces, post types)>

## الهدف والجمهور
<what the account is trying to achieve (sales, leads, reputation, fans, reach, community, streams, donations, votes...),
who it talks to, in what language and dialect; what success looks like for an account of this kind>

## المحتوى
<the content pillars you saw, with rough shares; the formats; how often it posts; who appears; recurring series>

## الصوت والهوية البصرية
<tone of voice; the visual identity as seen (colours, type, templates, logo use); how consistent it is>

## ما يجب الانتباه له في التحليل
<what the craft reviewers should weigh most for this kind of account, what is irrelevant for it, and risks particular
to it: factual accuracy for an information brand, product clarity for a shop, performance and sound for an artist,
timing and relatability for humour, sensitivity for news or politics>

## أسئلة للمستخدم
<only what the posts cannot answer and that would change the analysis; or "لا يوجد">
```

## Write `taxonomy.json`

```json
{
  "account_type": "company_b2b | company_b2c | brand_product | shop_ecommerce | creator_personal | artist_musician | media_news | memes_humor | education_tips | public_figure_politics | community_ngo | food_hospitality | health_beauty | sports | other",
  "account_type_detail": "one sentence",
  "report_language": "ar | en | ...",
  "main_language": "e.g. iraqi_arabic, msa, english, mixed_arabic_english",
  "goal": "one sentence",
  "success_signals": ["which signals matter most for this type, in order: plays, likes, comments, shares, saves, follows, clicks, sales, bookings..."],
  "topics": {"key_in_snake_case": {"label": "label in the report language", "definition": "what belongs here"}},
  "formats": {"key_in_snake_case": {"label": "...", "definition": "..."}},
  "custom_fields": [{"name": "snake_case", "type": "string | enum | bool | int", "values": ["for enum"], "definition": "what to record and why it matters for this account"}],
  "comment_categories_extra": {"key": {"label": "...", "definition": "..."}},
  "lenses": [{"key": "snake_case", "label": "...", "focus": "what a specialist would judge for this account type, e.g. humour timing, vocal performance, product close-ups, data accuracy"}],
  "panel": [{"key": "snake_case", "expert": "the specialist's role, e.g. scriptwriter and copy editor", "dimensions": ["script", "caption"], "focus": "what they look for on this account"}],
  "brand_reference": "the account's own visual identity as observed: colours, fonts, templates, logo",
  "accuracy_checks": ["things the reviewers must verify on every post for this account, e.g. numbers against their source, brand name spelling, prices, dates"],
  "people": {"P1 or a name": "role as seen, e.g. main presenter, host, the artist, guest"}
}
```

Rules for the scheme:
- `topics`: 8 to 18 values that cover what this account actually posts, specific enough to be useful ("قراءة نتائج
  تقرير" beats "معلومات"), plus `other`. `formats`: 8 to 16 values, likewise. Use what you saw.
- `custom_fields`: 0 to 4, only what later analysis needs and the standard coding lacks (a company: sector,
  product line; an artist: song or release; a shop: product and price shown; news: story type).
- `lenses`: 0 to 3 specialist angles beyond the standard dimensions (script, delivery, filming, editing, design,
  caption). `panel`: 4 to 6 experts that together cover all dimensions and lenses, each with a clear remit.
- Labels in the report language. Keys in English snake_case.
- `people`: the recurring faces you saw, by name only if the user or the posts name them; never guess a name,
  and never infer anyone's gender.

## Return
Three lines: the account type in a few words, the number of topics and formats, and any question for the user.
