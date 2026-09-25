# Asking the owner for their own data

When the account is the user's own, or the user can reach its owner, ask for what only the owner can see. It fills the
biggest gap in public data: Instagram shows likes, comments and plays to everyone, but reach, shares, saves, follows
from a post, watch time and the audience's make-up only to the account.

Ask once, in the user's language, as a short list, and say that everything is optional and the audit runs without it.
Whatever arrives goes in `profiles/<user>/audit/owner_data/`; `owner_data.py` reads the spreadsheets, and the
writers read the screenshots.

## What to ask for, most useful first

1. **Per-post export from Meta Business Suite** (business.facebook.com): Insights, then Content, choose Instagram,
   set the date range to cover the audit window, then Export (CSV or Excel). Every column it offers is useful; the
   ones that matter most are reach, views, shares, saves, follows and interactions, and the post's link.
   If the range is limited, several exports covering the window are fine.
2. **Which posts were boosted or run as ads**, and roughly when. A boosted post is judged against unboosted
   neighbours unfairly; the dataset marks it and leaves it out of the comparisons.
3. **Audience screenshots** from the Instagram app (professional dashboard, then Total followers): top cities and
   countries, age ranges, gender split, most active times.
4. **Account overview screenshots** for the window: accounts reached, accounts engaged, follower growth, and the
   split between followers and non-followers.
5. **Reel screenshots** for the five strongest and five weakest reels: the insights page of each (watch time,
   average watch time, and whatever retention figure Instagram shows).
6. **Anything outside Instagram** that the account is meant to drive, if the user wants it weighed: link-in-bio
   clicks, website visits, enquiries, sales or bookings by week.

## Rules
- Never ask for a password or a login code, and never sign in to the account yourself. The owner exports and sends
  files; that is all.
- A leads list, customer list or any file with personal contact details stays out of the report entirely: use counts
  only, if at all.
- Figures from the owner's data are cited as such in the report ("من بيانات الحساب نفسه").
