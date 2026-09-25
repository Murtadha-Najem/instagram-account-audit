"""Read what the account owner exported from Meta Business Suite or Instagram's professional dashboard.

usage: python owner_data.py <username>
reads every .csv / .xlsx in audit/owner_data/ (screenshots stay there for the writers to read)
writes audit/owner_metrics.json {shortcode: {reach, views, shares, saves, follows, ...}} and owner_data.md (what was found)

Column names differ by export and language, so columns are matched on keywords (English and Arabic). A row is tied to a
post by its permalink; rows without one are kept in the summary only.
"""
import json
import re
import sys

from common import root

FIELDS = {   # our name: keywords that identify the column (lower case)
    "reach": ["reach", "الوصول", "accounts reached"],
    "views": ["views", "impressions", "المشاهدات", "مرات الظهور", "plays"],
    "likes": ["likes", "الإعجابات", "تسجيلات الإعجاب"],
    "comments": ["comments", "التعليقات"],
    "shares": ["shares", "المشاركات", "مرات المشاركة"],
    "saves": ["saves", "الحفظ", "مرات الحفظ"],
    "follows": ["follows", "المتابعات", "follows from"],
    "profile_visits": ["profile visits", "زيارات الملف"],
    "interactions": ["interactions", "engagement", "التفاعلات"],
    "watch_time": ["watch time", "وقت المشاهدة", "average watch", "avg. watch"],
    "boosted": ["boost", "promoted", "ads", "مروج"],
}
CODE = re.compile(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


def frames(folder):
    import pandas as pd
    for f in sorted(folder.glob("*")):
        try:
            if f.suffix.lower() == ".csv":
                for enc in ("utf-8-sig", "utf-16", "cp1256"):
                    try:
                        yield f.name, pd.read_csv(f, encoding=enc)
                        break
                    except (UnicodeError, UnicodeDecodeError):
                        continue
            elif f.suffix.lower() in (".xlsx", ".xls"):
                for sheet, df in pd.read_excel(f, sheet_name=None).items():
                    yield f"{f.name}:{sheet}", df
        except Exception as e:
            print(f"  could not read {f.name}: {e}")


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def main():
    user = sys.argv[1].lstrip("@").lower()
    R = root(user)
    folder = R / "owner_data"
    if not folder.exists():
        print(f"no owner data: put exports in {folder}")
        return
    per_post, notes = {}, []
    for name, df in frames(folder):
        cols = {c: str(c).lower() for c in df.columns}
        link_col = next((c for c in df.columns if df[c].astype(str).str.contains("instagram.com/").any()), None)
        mapped = {field: next((c for c, low in cols.items() if any(k in low for k in keys)), None) for field, keys in FIELDS.items()}
        mapped = {k: v for k, v in mapped.items() if v is not None}
        notes.append(f"- {name}: {len(df)} rows; post links: {'yes (' + str(link_col) + ')' if link_col else 'no'}; "
                     f"columns used: {', '.join(f'{k}={v}' for k, v in mapped.items()) or 'none'}")
        if not link_col:
            continue
        for _, row in df.iterrows():
            m = CODE.search(str(row[link_col]))
            if not m:
                continue
            rec = per_post.setdefault(m.group(1), {"source": name})
            for field, col in mapped.items():
                v = row[col]
                rec[field] = (str(v).strip().lower() not in ("", "nan", "no", "false", "0")) if field == "boosted" else num(v)
    (R / "owner_metrics.json").write_text(json.dumps(per_post, ensure_ascii=False, indent=1), encoding="utf-8")
    shots = [f.name for f in folder.glob("*") if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".pdf")]
    (R / "owner_data.md").write_text("# Owner data\n\n" + "\n".join(notes) + f"\n\n- posts matched: {len(per_post)}\n"
                                     f"- screenshots and PDFs for the writers to read: {', '.join(shots) or 'none'}\n", encoding="utf-8")
    print((R / "owner_data.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
