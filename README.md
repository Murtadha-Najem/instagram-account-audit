# Instagram account audit

A toolkit for [Claude Code](https://claude.com/claude-code) that reads Instagram posts the way an analyst would, then
audits whole accounts: what the audience engages with, and how well the content is made.

It has one local pipeline and three skills built on it:

| skill | what it does |
|---|---|
| `/reel <link>` | Understands one reel, video or photo post: caption, speech (transcribed only when the screen does not already carry it), on-screen text, the song, and a few chosen frames. Cheap local checks decide what is worth sending to a model. |
| `/account-audit <link>` | A full audit of any account, of any kind and size: every post, reel, carousel, comment, liker, tagged post, partner and highlight; the people on screen; then a PDF report in two linked halves, engagement and craft. |
| `/repost-profile <link>` | A report on everything an account has reposted: types, timing, songs, the circle it reposts from, themes over time. |

## What `/account-audit` produces

1. **A first look before anything is spent.** It reads the profile and the latest posts, says what the account seems
   to be, and shows four modes (full, engagement only, content only, brief) with the time and tokens each would take
   for this account. Nothing starts until the user picks one.
2. **Understanding the account first.** An agent reads a spread sample of posts and writes a brief and a coding scheme
   for this kind of account: a company, an artist, a meme page or a news outlet are judged by different standards.
3. **Engagement.** Each post is compared with its neighbours in time (lift), so growth does not distort the picture.
   Comments are read and coded. Likers are split into the internal circle (the team, the account's own group, anyone
   who likes nearly everything over a long window) and genuine engagement. Partners, collabs, timing and the owner's
   own export (reach, shares, saves) when they provide it.
4. **Craft, apart from the numbers.** Reviewer agents go through every post as a scriptwriter, presentation coach,
   director of photography, editor, designer and copywriter would. An audio model listens to every video with speech,
   since the agents can only read. An expert panel then gives the account an overall verdict per dimension.
5. **A report** in the user's language (Arabic and English are built in), in the account's own colours and logo when
   given: findings with examples cited by topic, date and post ID, exhibit frames, before and after rewrites, errors to
   fix, and a playbook. The build checks itself for split headings, uncited posts and unknown IDs.

It asks for extra context (team members and their faces, the account's sister accounts, brand colours, the owner's
Meta Business Suite export) and uses it when given, but runs from nothing. Large accounts are collected in full at a
slow pace, with the option of a spare login.

## Requirements

- Python 3.11 or newer, [ffmpeg](https://ffmpeg.org/) on the PATH, and Microsoft Edge or Google Chrome (for PDFs).
- A Gemini API key for speech ([Google AI Studio](https://aistudio.google.com/) has a free tier).
- An Instagram login exported as a cookies file.
- Claude Code, for the skills. The pipeline also runs on its own: `python reel.py <link>`.

## Install

```bash
git clone https://github.com/Murtadha-Najem/instagram-account-audit.git
cd instagram-account-audit
pip install -r requirements.txt
python install.py            # copies the skills to ~/.claude/skills and points them at this folder
python install.py --models   # optional: audio tagger and face models (about 600 MB)
```

Then:
1. **Cookies.** Log in to Instagram in your browser, export the cookies with the extension "Get cookies.txt LOCALLY",
   and save the file as `~/.config/reel/cookies.txt`. Never share this file.
2. **Gemini.** Set `GEMINI_API_KEY`, or put one key per line in `~/.config/reel/gemini_keys.txt`. Several keys are
   rotated when one runs out of its daily quota.
3. **Check.** `python skills/account-audit/scripts/preflight.py` says what is ready and what is missing.

## Use

In Claude Code:

```
/reel https://www.instagram.com/reel/XXXXXXXXXXX/
/account-audit https://www.instagram.com/some.account/
/repost-profile some.account
```

Everything a run produces stays in this folder, under `data/` (downloads, frames, transcripts), `profiles/`
(collected accounts and reports) and `batch/`, all ignored by git.

## Responsible use

- Audit public accounts, your own, or accounts whose owners agreed. Private accounts are only visible as far as your
  login can see them.
- Collection uses your own logged-in session and is paced to look like a person browsing. Instagram still limits
  heavy use: for large accounts use a spare login, and stop when it answers with rate limits. You are responsible for
  following Instagram's terms.
- Faces are detected and matched on your machine; nothing is uploaded. Names come only from what you provide.
- Reports describe the account's own content. Commenters and likers are counted, not named.

## Layout

```
reel.py, batch.py, look.py   pipeline entry points: one post, many posts, a closer look at a processed post
reel/                        pipeline stages: download, video, OCR, audio, speech, bundle
skills/reel/                 the /reel skill
skills/account-audit/        the /account-audit skill: SKILL.md, scripts/, instructions/ (agent contracts),
                             references/, themes/
skills/repost-profile/       the /repost-profile skill
install.py                   installs the skills and optional models
```

## Licence

MIT, see [LICENSE](LICENSE). Part of `reel/video.py` adapts code from
[bradautomates/claude-video](https://github.com/bradautomates/claude-video) (MIT); see [THIRD_PARTY.md](THIRD_PARTY.md).

---

## بالعربي

مجموعة أدوات لـ Claude Code تحلل منشورات انستغرام، وتسوي تدقيق كامل لأي حساب مهما كان نوعه أو حجمه. التقرير بجزئين:
- **التفاعل:** وين يتفاعل الجمهور وعلى شنو، مع فصل التفاعل الحقيقي عن تفاعل الفريق والمعارف.
- **صناعة المحتوى، بعيداً عن الأرقام:** النص والكلمات والإلقاء والتصوير والمونتاج والتصميم والكابشن.

قبل ما تبدي، الأداة تفهم نوع الصفحة، وتعرض الكلفة بالوقت والتوكنز لكل وضع، وتنتظر الموافقة. التثبيت بالأوامر أعلاه.
