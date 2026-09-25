"""Merge everything known about a profile's reposts, compute the facts, and prepare every writer's input.

usage: python build_inputs.py <profile dir> [--theme-min 12] [--chrono-size 110]

reads   profile.json, links.json, context.json (optional), coding/*.json, records/*.md,
        the shared pipeline cache (metadata.json, media_raw.json, bundle.json) and the pipeline results
writes  dataset.json          one merged row per coded post, in repost order (oldest first)
        facts.md              every table the numbers writer and the synthesis writer need
        inputs/theme_*.md     one per theme group (small groups merged): header, digest, quotes, social; full record
                              only for strong-signal posts
        inputs/chronology_*.md  compact rows in time order
        inputs/signals.md     the reposter's notes and every strong signal
        inputs/plan.json      the writer jobs to run, with inputs, outputs and titles

context.json (optional, written by the orchestrator): {"utc_offset_hours": 3, "periods": [{"name", "from": "YYYY-MM",
"to": "YYYY-MM"}], "address": "second" | "third"}
"""
import argparse
import json
import math
import re
import statistics as S
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from taxonomy import (ARABIC_LANGS, EMO_AR, GROUP_AR, GROUP_TITLE, GROUPS, LANG_AR, WEEKDAYS, group_of,  # noqa: E402
                      month_long)

CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
PROJECT = Path(CONFIG["project_root"])
CACHE = PROJECT / "data" / "cache"


# ---------- loading ----------

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_record(path):
    text = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    body = m.group(2) if m else text
    title = re.search(r"^# (.+)$", body, re.M)
    sections = {}
    for part in re.split(r"^## ", body, flags=re.M)[1:]:
        head, _, content = part.partition("\n")
        sections[head.strip()] = content.strip()
    return (title.group(1).strip() if title else ""), sections, text


def utc(text):
    try:
        return datetime.strptime(text.replace(" UTC", "")[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def raw_layer(raw, target_id, target_name, viewer_is_target):
    """Repost time from the raw media response, plus the social layer that is only meaningful for one's own account."""
    notes = (raw.get("media_notes") or {}).get("items") or []
    mine = [n for n in notes if str((n.get("user") or {}).get("pk") or n.get("user_id")) == target_id
            or (n.get("user") or {}).get("username", "").lower() == target_name]
    out = {"repost_at": datetime.fromtimestamp(mine[0]["created_at"], timezone.utc) if mine and mine[0].get("created_at") else None}
    clips = raw.get("clips_metadata") or {}
    music_info = clips.get("music_info") or (raw.get("music_metadata") or {}).get("music_info") or {}
    music = music_info.get("music_asset_info") or {}
    cons = music_info.get("music_consumption_info") or {}
    osound = clips.get("original_sound_info") or {}
    owner = raw.get("owner") or raw.get("user") or {}
    out.update({
        "music_title": music.get("title"), "music_artist": music.get("display_artist"),
        "music_explicit": bool(music.get("is_explicit")), "music_trending": bool(cons.get("is_trending_in_clips")),
        "sound_from": (osound.get("ig_artist") or {}).get("username") if osound and (osound.get("ig_artist") or {}).get("username") not in (None, owner.get("username")) else None,
        "caption_edited": bool(raw.get("caption_is_edited")),
    })
    if viewer_is_target:
        others = [n for n in notes if n not in mine]
        out.update({
            "follows_owner": bool((owner.get("friendship_status") or {}).get("following")),
            "friends_who_liked": [u.get("username") for u in raw.get("facepile_top_likers") or []],
            "reactions": [{"by": (r.get("user") or {}).get("username"), "name": (r.get("user") or {}).get("full_name"),
                           "type": r.get("reaction_type")} for n in mine for r in n.get("reactions") or []],
            "other_reposters": [{"by": (n.get("user") or {}).get("username"), "note": n.get("text"),
                                 "at": datetime.fromtimestamp(n["created_at"], timezone.utc).isoformat() if n.get("created_at") else None}
                                for n in others],
        })
    return out


def build_rows(p, profile, context):
    tz = timezone(timedelta(hours=float(context.get("utc_offset_hours", 3))))
    links = load_json(p / "links.json", [])
    results = {}
    res_path = PROJECT / "batch" / f"profile_{profile['username'].lower()}" / "results.jsonl"
    if res_path.exists():
        for line in res_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("status") == "ok":
                    results[r["shortcode"]] = r
    rows, missing = [], []
    for item in links:
        code = item["shortcode"]
        coding = load_json(p / "coding" / f"{code}.json")
        records = list((p / "records").glob(f"*_{code}.md"))
        if not coding or not records:
            missing.append(code)
            continue
        title, sections, _ = parse_record(records[0])
        d = CACHE / code
        meta = load_json(d / "metadata.json") or (load_json(d / "post.json", {}) or {}).get("details") or {}
        bundle = load_json(d / "bundle.json", {})
        raw = load_json(d / "media_raw.json", {})
        layer = raw_layer(raw, profile["user_id"], profile["username"].lower(), profile.get("viewer_is_target"))
        posted = utc(meta.get("posted_utc") or "")
        rep = layer.pop("repost_at")
        local = rep.astimezone(tz) if rep else None
        song = (bundle.get("audio") or {}).get("song") or {}
        owner = meta.get("owner") or {}
        primary = coding.get("primary_theme", "other")
        row = {
            "order": item["order"], "shortcode": code, "url": item["href"],
            "owner": owner.get("username") or item.get("owner"), "owner_name": owner.get("full_name"),
            "owner_verified": owner.get("verified"), "owner_account_type": owner.get("account_type"),
            "posted_utc": posted.isoformat() if posted else None,
            "repost_utc": rep.isoformat() if rep else None,
            "repost_local": local.strftime("%Y-%m-%d %H:%M") if local else None,
            "repost_date": local.strftime("%Y-%m-%d") if local else None,
            "repost_weekday": local.strftime("%A") if local else None,
            "repost_hour": local.hour if local else None,
            "lag_days": round((rep - posted).total_seconds() / 86400, 2) if rep and posted else None,
            "note": item.get("note_text") or "",
            "format": (results.get(code) or {}).get("format") or meta.get("media_type"),
            "duration_s": (results.get(code) or {}).get("duration_s") or meta.get("duration_s"),
            "plays": meta.get("plays"), "likes": None if meta.get("counts_hidden_by_owner") else meta.get("likes"),
            "comments": meta.get("comments"), "reposts_count": meta.get("reposts"),
            "audio_kind": (bundle.get("audio") or {}).get("kind"),
            "song_title": layer.get("music_title") or song.get("title"),
            "song_artist": layer.get("music_artist") or song.get("artist"),
            "song_source": "Instagram" if layer.get("music_title") else (song.get("source") if song else None),
            "hashtags": meta.get("hashtags") or [], "location": (meta.get("location") or {}).get("name"),
            "ai_label": meta.get("ai_label_detection"),
            "caption": ((bundle.get("meta") or {}).get("caption") or "")[:500],
            "title": title, "record": str(records[0]),
            "description": sections.get("الوصف", ""),
            **{k: v for k, v in layer.items() if not k.startswith("music_title") and k != "music_artist"},
            **{f"c_{k}": v for k, v in coding.items() if k != "shortcode"},
            "group": group_of(primary),
            "groups_all": sorted({group_of(t) for t in coding.get("themes") or [primary]}),
        }
        row["month"] = (row["repost_date"] or (row["posted_utc"] or "")[:10])[:7]
        rows.append(row)
    # Oldest first. Without repost times, the grid order (newest first) is the only order there is.
    rows.sort(key=lambda r: (r["repost_utc"] or "", -r["order"]) if any(x["repost_utc"] for x in rows) else -r["order"])
    return rows, missing


def assign_periods(rows, context):
    months = sorted({r["month"] for r in rows if r["month"]})
    periods = context.get("periods")
    if not periods and months:
        chunk = max(1, math.ceil(len(months) / 5))
        periods = []
        for i in range(0, len(months), chunk):
            a, b = months[i], months[min(i + chunk, len(months)) - 1]
            periods.append({"name": month_long(a) if a == b else f"{month_long(a)} إلى {month_long(b)}", "from": a, "to": b})
    for r in rows:
        r["period"] = next((x["name"] for x in periods if x["from"] <= (r["month"] or "") <= x["to"]), "خارج المراحل")
    return periods or []


# ---------- tables ----------

def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "-"


def md_table(headers, body):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def count_table(title, counter, total, labels=None, top=None):
    body = [(labels.get(k, k) if labels else k, v, pct(v, total)) for k, v in counter.most_common(top)]
    return f"\n### {title}\n" + md_table(["القيمة", "عدد", "النسبة"], body) + "\n"


def cross(title, rows, row_key, row_order, col_fn, cols, col_labels=None, multi=False):
    body = []
    for k in row_order:
        sub = [r for r in rows if r[row_key] == k]
        if not sub:
            continue
        cells = []
        for c in cols:
            n = sum(1 for r in sub if (c in col_fn(r) if multi else col_fn(r) == c))
            cells.append(f"{n} ({pct(n, len(sub))})")
        body.append([k, len(sub)] + cells)
    heads = [row_key, "عدد"] + [(col_labels or {}).get(c, c) for c in cols]
    return f"\n### {title}\n" + md_table(heads, body) + "\n"


def facts(rows, profile, periods, context):
    n = len(rows)
    own = bool(profile.get("viewer_is_target"))
    timed = [r for r in rows if r["repost_utc"]]
    L = [f"# Facts for @{profile['username']}",
         f"posts analysed: {n} of {profile.get('reposts')} collected | repost times known for {len(timed)} | "
         f"own account of the viewer: {own} | address: {context.get('address', 'second' if own else 'third')}",
         f"periods: " + "; ".join(f"{x['name']} ({x['from']} to {x['to']})" for x in periods)]
    charts = ["months", "groups", "groups_period", "groups_month", "language_period", "emotions"]
    if len(timed) >= 0.8 * n:
        charts += ["hours", "heatmap", "lag"]
    if own:
        charts += ["reactions_month", "reactions_group", "follows_group"]
    L.append("charts available: " + ", ".join(charts))
    if timed:
        L.append(f"first repost {timed[0]['repost_local']}, last {timed[-1]['repost_local']}")

    # Rhythm
    L.append("\n## الإيقاع")
    months = sorted({r["month"] for r in rows})
    body = []
    for m in months:
        sub = [r for r in rows if r["month"] == m]
        night = sum(1 for r in sub if r["repost_hour"] is not None and (r["repost_hour"] >= 18 or r["repost_hour"] < 5))
        top = ", ".join(f"{t} {c}" for t, c in Counter(r["c_primary_theme"] for r in sub).most_common(3))
        body.append([month_long(m), len(sub), len({r["repost_date"] for r in sub if r["repost_date"]}), night, top,
                     f'{S.median([r["plays"] for r in sub if r["plays"]] or [0]):,.0f}'])
    L.append(md_table(["الشهر", "ريبوستات", "أيام نشر", "بعد 6 مساءً أو قبل 5 فجراً", "أكثر المواضيع", "مشاهدات وسطية"], body))
    if timed:
        L.append("\nhours: " + ", ".join(f"{h}:{sum(1 for r in timed if r['repost_hour'] == h)}" for h in range(24)))
        L.append("weekdays: " + ", ".join(f"{ar} {sum(1 for r in timed if r['repost_weekday'] == en)}" for en, ar in WEEKDAYS))
        ts = [datetime.fromisoformat(r["repost_utc"]) for r in timed]
        gaps = sorted(((round((b - a).total_seconds() / 86400, 1), timed[i]["repost_local"], timed[i + 1]["repost_local"])
                       for i, (a, b) in enumerate(zip(ts, ts[1:]))), reverse=True)
        L.append("\n### أطول فترات السكوت\n" + md_table(["أيام", "آخر ريبوست قبلها", "أول ريبوست بعدها"], gaps[:10]))
        if len(ts) > 1:
            L.append(f"\nmedian gap days {S.median([(b - a).total_seconds() / 86400 for a, b in zip(ts, ts[1:])]):.2f}; "
                     f"reposts within 30 min of the previous: {sum(1 for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() < 1800)}")
        band = defaultdict(Counter)
        for r in timed:
            h = r["repost_hour"]
            band["00-04" if h < 5 else "05-11" if h < 12 else "12-17" if h < 18 else "18-23"][r["group"]] += 1
        L.append("\n### المجموعات حسب وقت اليوم\n" + md_table(["الوقت"] + [GROUP_AR[g] for g in GROUPS],
                 [[b] + [band[b][g] for g in GROUPS] for b in ("00-04", "05-11", "12-17", "18-23")]))
        days = defaultdict(list)
        for r in timed:
            days[r["repost_date"]].append(r)
        busy = sorted(days.items(), key=lambda kv: -len(kv[1]))[:10]
        L.append("\n### أكثف الأيام")
        for day, rs in busy:
            if len(rs) < 3:
                break
            L.append(f"- {day} ({len(rs)}): " + " | ".join(f"{r['repost_local'][11:]} {r['title'][:70]}" for r in rs))
        lags = [r["lag_days"] for r in timed if r["lag_days"] is not None]
        if lags:
            buckets = [("<6h", 0, .25), ("6-24h", .25, 1), ("1-3d", 1, 3), ("3-7d", 3, 7), ("7-30d", 7, 30), (">30d", 30, 1e9)]
            L.append("\nlag after posting: " + ", ".join(f"{b} {sum(1 for x in lags if lo < x <= hi or (lo == 0 and x <= hi))}" for b, lo, hi in buckets)
                     + f"; median {S.median(lags):.1f} days, max {max(lags):.0f}")
            L.append("median lag by group: " + ", ".join(f"{GROUP_AR[g]} {S.median(v):.1f}" for g in GROUPS
                     if (v := [r['lag_days'] for r in timed if r['group'] == g and r['lag_days'] is not None])))
    plays = [r["plays"] for r in rows if r["plays"]]
    if plays:
        L.append(f"\nplays: median {S.median(plays):,.0f}; >1M {sum(p > 1e6 for p in plays)}; >10M {sum(p > 1e7 for p in plays)}; <100k {sum(p < 1e5 for p in plays)}")
        L.append("\n### أشهر المنشورات\n" + md_table(["مشاهدات", "الحساب", "المنشور", "الملاحظة"],
                 [[f"{r['plays']:,}" if r["plays"] else "-", "@" + str(r["owner"]), r["title"][:80], r["note"]]
                  for r in sorted(rows, key=lambda r: -(r["plays"] or 0))[:10]]))
        small = [r for r in rows if (r["plays"] and r["plays"] < 20000) or (r["reposts_count"] is not None and r["reposts_count"] < 100)]
        L.append("\n### منشورات صغيرة الانتشار\n" + md_table(["الحساب", "مشاهدات", "ريبوستات", "المنشور"],
                 [["@" + str(r["owner"]), r["plays"], r["reposts_count"], r["title"][:80]] for r in small]))

    # Types
    L.append("\n## النوع")
    L.append(count_table("المجموعة (الموضوع الرئيسي)", Counter(r["group"] for r in rows), n, GROUP_AR))
    L.append(count_table("المجموعة (أي موضوع)", Counter(g for r in rows for g in r["groups_all"]), n, GROUP_AR))
    L.append(count_table("المواضيع التفصيلية (أي موضوع)", Counter(t for r in rows for t in r["c_themes"] or []), n))
    L.append(cross("المجموعات حسب المرحلة", rows, "period", [x["name"] for x in periods], lambda r: r["group"], list(GROUPS), GROUP_AR))
    L.append(cross("المجموعات حسب الشهر", rows, "month", months, lambda r: r["group"], list(GROUPS), GROUP_AR))
    forms = Counter(r["c_form"] for r in rows)
    L.append("\n### الشكل\n" + md_table(["الشكل", "عدد", "مثال"],
             [[f, c, next(r["title"][:70] for r in rows if r["c_form"] == f)] for f, c in forms.most_common()]))
    durs = [r["duration_s"] for r in rows if r["duration_s"]]
    if durs:
        L.append(f"\ndurations: median {S.median(durs):.1f}s; <8s {sum(d < 8 for d in durs)}; 8-15 {sum(8 <= d < 15 for d in durs)}; "
                 f"15-30 {sum(15 <= d < 30 for d in durs)}; 30-60 {sum(30 <= d < 60 for d in durs)}; 60+ {sum(d >= 60 for d in durs)}; "
                 f"photo posts {sum(1 for r in rows if not r['duration_s'])}")
    L.append(count_table("اللغة", Counter(r["c_language"] for r in rows), n, LANG_AR))
    L.append(cross("اللغة حسب المجموعة", rows, "group", list(GROUPS), lambda r: r["c_language"],
                   [k for k, _ in Counter(r["c_language"] for r in rows).most_common(7)], LANG_AR))
    L.append(cross("اللغة حسب المرحلة", rows, "period", [x["name"] for x in periods], lambda r: r["c_language"],
                   [k for k, _ in Counter(r["c_language"] for r in rows).most_common(7)], LANG_AR))
    L.append(count_table("الإطار الثقافي", Counter(r["c_cultural_frame"] for r in rows), n))
    L.append(count_table("العاطفة", Counter(r["c_emotion"] for r in rows), n, EMO_AR))
    L.append(cross("العاطفة حسب المرحلة", rows, "period", [x["name"] for x in periods], lambda r: r["c_emotion"],
                   [k for k, _ in Counter(r["c_emotion"] for r in rows).most_common(8)], EMO_AR))
    L.append(count_table("النبرة (متعددة)", Counter(t for r in rows for t in r["c_tone"] or []), n))
    L.append(count_table("نوع النكتة", Counter(r["c_humor_type"] for r in rows), n))
    L.append(count_table("الشدة العاطفية", Counter(str(r["c_intensity"]) for r in rows), n))
    L.append(count_table("القيم (متعددة)", Counter(v for r in rows for v in r["c_values"] or []), n))
    L.append(cross("القيم حسب المرحلة", rows, "period", [x["name"] for x in periods], lambda r: r["c_values"] or [],
                   [k for k, _ in Counter(v for r in rows for v in r["c_values"] or []).most_common(8)], multi=True))
    L.append(count_table("شنو يقول الريبوست عن صاحبه", Counter(r["c_self_reference"] for r in rows), n))
    L.append(cross("المرجع حسب المجموعة", rows, "group", list(GROUPS), lambda r: r["c_self_reference"],
                   [k for k, _ in Counter(r["c_self_reference"] for r in rows).most_common(7)]))
    L.append(count_table("لمن موجّه", Counter(r["c_relationship_target"] for r in rows), n))
    L.append(count_table("منو يظهر", Counter(r["c_people_featured"] for r in rows), n))
    bait = [r for r in rows if r["c_caption_bait"]]
    L.append(f"\ncaption bait: {len(bait)} ({pct(len(bait), n)}); by group: " + ", ".join(f"{GROUP_AR[g]} {c}" for g, c in Counter(r['group'] for r in bait).most_common())
             + f"; captions edited: {sum(1 for r in rows if r.get('caption_edited'))}")
    L.append("hashtags: " + ", ".join(f"{h} {c}" for h, c in Counter(h.lower() for r in rows for h in r["hashtags"]).most_common(25)))
    L.append("locations: " + "; ".join(f"{r['month']} {r['location']} (@{r['owner']})" for r in rows if r["location"]))
    L.append(f"account types: {dict(Counter(r['owner_account_type'] for r in rows))}; verified owners: "
             + ", ".join(f"@{r['owner']}" for r in rows if r["owner_verified"]))
    owners = Counter(r["owner"] for r in rows)
    L.append(f"distinct accounts {len(owners)}; accounts reposted from more than once: " + ", ".join(
        f"@{o} {c} ({next(r['owner_name'] or '' for r in rows if r['owner'] == o)}; {next(r['month'] for r in rows if r['owner'] == o)} to {[r['month'] for r in rows if r['owner'] == o][-1]})"
        for o, c in owners.most_common() if c > 1))
    reused = [r for r in rows if r.get("sound_from")]
    if reused:
        L.append("sound taken from another creator: " + "; ".join(f"{r['month']} @{r['owner']} sound from @{r['sound_from']}: {r['title'][:50]}" for r in reused))

    # Own-account social layer
    if own:
        L.append("\n## الدائرة (حساب المشاهد نفسه)")
        follows = [r for r in rows if r.get("follows_owner")]
        L.append(f"from accounts the owner follows: {len(follows)} of {n}; by group: " + ", ".join(
            f"{GROUP_AR[g]} {sum(1 for r in follows if r['group'] == g)}/{sum(1 for r in rows if r['group'] == g)}" for g in GROUPS))
        L.append("followed accounts: " + ", ".join(f"@{o} {c}" for o, c in Counter(r["owner"] for r in follows).most_common()))
        reacts = [(r, x) for r in rows for x in r.get("reactions") or []]
        L.append(f"reactions on the reposts: {len(reacts)} on {sum(1 for r in rows if r.get('reactions'))} posts from "
                 f"{len({x['by'] for _, x in reacts})} people; types: {dict(Counter(x['type'] for _, x in reacts))}")
        L.append("reactions per repost by month: " + ", ".join(
            f"{m} {sum(len(r.get('reactions') or []) for r in rows if r['month'] == m) / max(1, sum(1 for r in rows if r['month'] == m)):.2f}" for m in months))
        L.append("reactions per repost by group: " + ", ".join(
            f"{GROUP_AR[g]} {sum(len(r.get('reactions') or []) for r in rows if r['group'] == g) / max(1, sum(1 for r in rows if r['group'] == g)):.2f}" for g in GROUPS))
        L.append("zero-reaction reposts by group: " + ", ".join(f"{GROUP_AR[g]} {c}" for g, c in Counter(r["group"] for r in rows if not r.get("reactions")).most_common()))
        with_note = [r for r in rows if r["note"]]
        if with_note:
            L.append(f"reactions with a note {sum(len(r.get('reactions') or []) for r in with_note) / len(with_note):.2f} vs without "
                     f"{sum(len(r.get('reactions') or []) for r in rows if not r['note']) / max(1, n - len(with_note)):.2f}")
        L.append("\n### أكثر الريبوستات تفاعلاً\n" + md_table(["تفاعلات", "اليوم", "المنشور", "نشروه منه (NOTE_ON_NOTE)"],
                 [[len(r["reactions"]), r["repost_date"], r["title"][:70], ", ".join("@" + x["by"] for x in r["reactions"] if x["type"] == "NOTE_ON_NOTE")]
                  for r in sorted(rows, key=lambda r: -len(r.get("reactions") or []))[:15]]))
        people = defaultdict(lambda: {"n": 0, "types": Counter(), "groups": Counter(), "months": [], "name": ""})
        for r, x in reacts:
            e = people[x["by"]]
            e["n"] += 1
            e["types"][x["type"]] += 1
            e["groups"][GROUP_AR[r["group"]]] += 1
            e["months"].append(r["month"])
            e["name"] = x["name"] or ""
        likers = Counter(u for r in rows for u in r.get("friends_who_liked") or [])
        L.append("\n### أكثر الناس تفاعلاً\n" + md_table(["الحساب", "الاسم", "تفاعلات", "من", "إلى", "نشر منه", "لايك على الأصل", "المجموعات"],
                 [["@" + k, e["name"], e["n"], min(e["months"]), max(e["months"]), e["types"]["NOTE_ON_NOTE"], likers.get(k, 0),
                   ", ".join(f"{g} {c}" for g, c in e["groups"].most_common(3))]
                  for k, e in sorted(people.items(), key=lambda kv: -kv[1]["n"])[:20]]))
        co = defaultdict(lambda: [0, 0])
        for r in rows:
            for o in r.get("other_reposters") or []:
                co[o["by"]][0] += 1
                if o["at"] and r["repost_utc"] and o["at"] > r["repost_utc"]:
                    co[o["by"]][1] += 1
        L.append(f"\nco-reposters (people followed who reposted the same post): {len(co)}; posts shared {sum(1 for r in rows if r.get('other_reposters'))}; "
                 + ", ".join(f"@{k} {v[0]} (after {v[1]})" for k, v in sorted(co.items(), key=lambda kv: -kv[1][0])[:10]))
        L.append("notes left by co-reposters: " + "; ".join(f"@{o['by']} on {r['repost_date']}: {o['note']}" for r in rows for o in r.get("other_reposters") or [] if o.get("note")))

    # Notes
    notes = [r for r in rows if r["note"]]
    L.append(f"\n## ملاحظات صاحب الحساب ({len(notes)})\n" + md_table(["الوقت", "الملاحظة", "المجموعة", "المنشور", "تفاعلات"],
             [[r["repost_local"] or r["month"], r["note"], GROUP_AR[r["group"]], r["title"][:70], len(r.get("reactions") or [])] for r in notes]))

    # Music
    songs = [r for r in rows if r["song_title"]]
    L.append(f"\n## الموسيقى\nposts with an identified song: {len(songs)} of {n} (Instagram tag {sum(1 for r in songs if r['song_source'] == 'Instagram')}); "
             f"explicit {sum(1 for r in songs if r.get('music_explicit'))}; trending when reposted {sum(1 for r in songs if r.get('music_trending'))}")
    L.append(md_table(["الشهر", "الأغنية", "الفنان", "الحساب", "المجموعة", "المنشور"],
             [[r["month"], r["song_title"], r["song_artist"], "@" + str(r["owner"]), GROUP_AR[r["group"]], r["title"][:60]] for r in songs]))
    rep = Counter(re.sub(r"\s*[\(\[].*$", "", r["song_title"].lower()).strip() for r in songs)
    L.append("\nrepeated songs: " + "; ".join(f"{k} x{c}: " + " / ".join(f"{r['repost_date'] or r['month']} {r['title'][:40]}" for r in songs if re.sub(r'\s*[\(\[].*$', '', r['song_title'].lower()).strip() == k)
                                          for k, c in rep.most_common() if c > 1))
    L.append("artists: " + ", ".join(f"{a} {c}" for a, c in Counter(r["song_artist"] for r in songs).most_common(40)))
    arab = lambda r: bool(re.search(r"[؀-ۿ]", f"{r['song_title']}{r['song_artist']}")) or r["c_language"] in ARABIC_LANGS and r["c_form"] in ("song_clip_with_visuals", "lyrics_on_screen")  # noqa: E731
    L.append("Arabic songs (approximate) by period: " + ", ".join(f"{x['name']} {sum(1 for r in songs if r['period'] == x['name'] and arab(r))}/{sum(1 for r in songs if r['period'] == x['name'])}" for x in periods))
    return "\n".join(L) + "\n", charts


# ---------- writer inputs ----------

def header(r, own):
    social = ""
    if own:
        social = (f"\n- social: follows account {'yes' if r.get('follows_owner') else 'no'}; reactions {len(r.get('reactions') or [])}"
                  + (" by " + ", ".join(sorted({x['by'] for x in r['reactions']})) if r.get("reactions") else "")
                  + "".join(f"; also reposted by @{o['by']}" + (f" ('{o['note']}')" if o.get("note") else "") for o in r.get("other_reposters") or []))
    return (f"### {r['shortcode']} | {r['repost_local'] or ('~' + r['month'])} | @{r['owner']} ({r['owner_name'] or ''})\n"
            f"- {r['title']}\n- reach: plays {r['plays']}, likes {r['likes']}, comments {r['comments']}, reposts {r['reposts_count']}; "
            f"{r['format']} {r['duration_s'] or ''}s; posted {(r['posted_utc'] or '')[:10]}, lag {r['lag_days']} days\n"
            f"- note by the reposter: {r['note'] or '(none)'}\n"
            f"- song: {r['song_title'] or '-'} / {r['song_artist'] or '-'}{' (explicit)' if r.get('music_explicit') else ''}{' (trending)' if r.get('music_trending') else ''}\n"
            f"- coding: {r['group']} | {', '.join(r['c_themes'] or [])} | {r['c_form']} | {r['c_language']} | {r['c_emotion']} {r['c_intensity']}/5 | "
            f"{', '.join(r['c_tone'] or [])} | humor {r['c_humor_type']} | values {', '.join(r['c_values'] or []) or '-'} | {r['c_self_reference']} -> {r['c_relationship_target']}"
            f"{social}\n- digest: {r.get('c_digest_ar', '')}\n- quotes: {' || '.join(r.get('c_quotes') or []) or '-'}\n"
            f"- stance: {r.get('c_stance_ar', '')}\n- signal ({r['c_signal_strength']}/5): {r.get('c_signal_ar', '')}\n- record: {r['record']}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile_dir")
    ap.add_argument("--theme-min", type=int, default=12, help="groups with fewer posts are merged into one file")
    ap.add_argument("--chrono-size", type=int, default=110)
    args = ap.parse_args()
    p = Path(args.profile_dir).resolve()
    profile = load_json(p / "profile.json")
    context = load_json(p / "context.json", {}) or {}
    own = bool(profile.get("viewer_is_target"))
    address = context.get("address") or ("second" if own else "third")
    rows, missing = build_rows(p, profile, context)
    if not rows:
        sys.exit("no coded posts yet")
    periods = assign_periods(rows, context)
    (p / "dataset.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    text, charts = facts(rows, profile, periods, context)
    (p / "facts.md").write_text(text, encoding="utf-8")

    inp = p / "inputs"
    inp.mkdir(exist_ok=True)
    for old in inp.glob("*"):
        old.unlink()
    head = f"address: {address} | account: @{profile['username']} | own account of the viewer: {own}\n"
    plan = []
    sizes = Counter(r["group"] for r in rows)
    files = [[g] for g in GROUPS if sizes[g] >= args.theme_min]
    small = [g for g in GROUPS if 0 < sizes[g] < args.theme_min]
    if small:
        if sum(sizes[g] for g in small) >= args.theme_min or not files:
            files.append(small)
        else:  # too few even together: fold them into the smallest full group
            min(files, key=lambda gs: sum(sizes[g] for g in gs)).extend(small)
    for i, groups in enumerate(files):
        folded = len(groups) > 1 and sizes[groups[0]] >= args.theme_min  # a full group that absorbed tiny ones
        name = groups[0] if folded else ("_".join(groups) if len(groups) < 3 else "mixed")
        if folded:
            title = GROUP_TITLE[groups[0]] + " (ومعها " + " و".join(GROUP_AR[g] for g in groups[1:]) + ")"
        else:
            title = " و".join(GROUP_TITLE[g] for g in groups) if len(groups) < 3 else "، ".join(GROUP_AR[g] for g in groups)
        sel = [r for r in rows if r["group"] in groups]
        also = [r for r in rows if r["group"] not in groups and any(g in groups for g in r["groups_all"])]
        parts = [head, f"# {title}: {len(sel)} posts, oldest first\n"]
        # Full records only for the strongest signals, capped so a file stays readable in a few passes.
        strong = {r["shortcode"] for r in sorted(sel, key=lambda r: (-r["c_signal_strength"], not r["note"]))[:12]
                  if r["c_signal_strength"] >= 4}
        for r in sel:
            block = header(r, own)
            if r["shortcode"] in strong:
                block += "\n#### full record (strong signal)\n" + Path(r["record"]).read_text(encoding="utf-8") + "\n"
            parts.append(block)
        parts.append(f"\n# Posts from other groups that also touch this one ({len(also)})\n")
        parts += [f"- {r['repost_local'] or r['month']} {r['shortcode']} @{r['owner']} [{r['group']}] {r['title']} | {r.get('c_digest_ar', '')[:160]} | note: {r['note'] or '-'}" for r in also]
        path = inp / f"theme_{name}.md"
        path.write_text("\n".join(parts), encoding="utf-8")
        plan.append({"role": "theme", "title": title, "input": str(path), "output": str(p / "sections" / f"1{i}_{name}.md"), "posts": len(sel)})

    # Chronology in balanced chunks that end on month boundaries.
    chunks, cur = [], []
    target = math.ceil(len(rows) / math.ceil(len(rows) / args.chrono_size))
    for r in rows:
        if cur and len(cur) >= target * 0.85 and r["month"] != cur[-1]["month"]:
            chunks.append(cur)
            cur = []
        cur.append(r)
    if cur:
        if chunks and len(cur) < target * 0.5:  # a short tail joins the previous chunk
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    for i, chunk in enumerate(chunks):
        a, b = month_long(chunk[0]["month"]), month_long(chunk[-1]["month"])
        title = f"شهر بشهر: {a} إلى {b}" if a != b else f"شهر بشهر: {a}"
        lines = [head, f"# {title}: {len(chunk)} posts in time order\n"]
        for r in chunk:
            lines.append(f"### {r['repost_local'] or '~' + r['month']} ({r['repost_weekday'] or ''}) {r['shortcode']} @{r['owner']}\n"
                         f"- {r['title']} | {GROUP_AR[r['group']]} | {EMO_AR.get(r['c_emotion'], r['c_emotion'])} | song: {r['song_title'] or '-'} / {r['song_artist'] or '-'}\n"
                         f"- note: {r['note'] or '-'} | reactions: {len(r.get('reactions') or []) if own else 'n/a'} | plays {r['plays']} | lag {r['lag_days']} days\n"
                         f"- digest: {r.get('c_digest_ar', '')}\n- quotes: {' || '.join(r.get('c_quotes') or []) or '-'}\n")
        path = inp / f"chronology_{i + 1}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        plan.append({"role": "chronology", "title": title, "input": str(path), "output": str(p / "sections" / f"2{i}_chronology.md"), "posts": len(chunk)})

    sig = [head, "# Notes and strong signals, oldest first\n"]
    sig += [f"- {r['repost_local'] or r['month']} {r['shortcode']} [{GROUP_AR[r['group']]}; {r['c_emotion']}; {r['c_self_reference']} -> {r['c_relationship_target']}] "
            f"{r['title']} | note: {r['note'] or '-'} | signal {r['c_signal_strength']}: {r.get('c_signal_ar', '')}"
            for r in rows if r["note"] or r["c_signal_strength"] >= 4]
    (inp / "signals.md").write_text("\n".join(sig), encoding="utf-8")
    plan.append({"role": "numbers", "title": "الأرقام: الإيقاع والنوع والدائرة والموسيقى", "input": str(p / "facts.md"),
                 "output": str(p / "sections" / "01_numbers.md"), "charts": charts})
    plan.append({"role": "synthesis", "title": "تحليل الشخصية", "input": str(inp / "signals.md"), "facts": str(p / "facts.md"),
                 "sections_dir": str(p / "sections"), "output": str(p / "sections" / "90_portrait.md"), "after": "all other writers"})
    (inp / "plan.json").write_text(json.dumps({"address": address, "context": str(p / "context.md"), "jobs": plan}, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "sections").mkdir(exist_ok=True)
    print(f"rows {len(rows)} | not yet coded {len(missing)} | periods {len(periods)} | writer jobs {len(plan)}")
    for job in plan:
        print(f"  {job['role']}: {job['title']} ({job.get('posts', '')}) -> {Path(job['output']).name}")


if __name__ == "__main__":
    main()
