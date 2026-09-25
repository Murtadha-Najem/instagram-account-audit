# Method notes (for the account-and-method section and for judgement calls)

## Performance: lift
Raw numbers do not compare across a year: accounts grow, the algorithm shifts, a partner's audience comes and goes.
Each post is compared with its neighbours instead: lift = the post's value divided by the median of the same metric
over the 4 posts of the same kind on each side (reels on plays, photos and carousels on likes; with the owner's export
also reach, shares and saves). 1.0 is typical for its time; 2.0 is twice its neighbours.
- Posts younger than 72 hours are excluded (their numbers are still climbing), and so are posts the owner says were
  boosted. Both stay in the appendix.
- Groups with fewer than 5 posts are hints. Every comparison is an association, not a proven cause.
- A collab reel shown to a partner's audience is still judged against the account's own neighbours; partner size is
  reported beside it.

## Genuine engagement and the internal circle
Some accounts like everything a page posts, whatever it is: the team, friends, the company's other accounts. They
make weak posts look fine. A liker is judged over their own active window (first to last post they liked): if they
liked more than half of the posts they could have seen, over at least 6 posts and 60 days, they are habitual. The
account itself, its group accounts and handles the user names as team always count as internal. Genuine likes = likes
minus internal likers; genuine lift is computed the same way as lift.
- Instagram shows about 100 likers per post, so only posts with a nearly complete list (90%) are used to judge
  habits. On large accounts few posts qualify and the analysis is skipped, with a note.
- Habitual accounts that are not named as team are counted, never named, in the report.

## People on screen
Faces are detected at 2 frames a second and matched locally; nothing leaves the machine. A person counts as present
in a post with 3 or more matched frames. Named references come only from the user; everyone else who recurs is a
numbered person, named only if the user names them. Nobody's name or gender is inferred.

## What the audio model hears
Gemini listens to each video with speech and rates pace, energy, clarity, confidence, pauses, fillers, sound quality
and music balance. The reviewing agents see frames and transcripts but cannot hear, so voice judgements come only
from this file.

## Limits to state in the report
- Public data has no reach, shares, saves, watch time or audience make-up unless the owner supplied them.
- Comments deleted or hidden by the account are not visible; counters include them.
- Stories are only visible through highlights.
- Play counts on collab reels include the partner's audience.
- Scores from reviewers are judgements, made to a written standard and backed by examples, not measurements.

## Large accounts
- Collection is never cut: everything in the window is collected at the slow pace, over a longer time. The user is
  told the time in advance and offered a spare login so the main account carries no risk.
- Review can be sampled if the user chooses: a stratified sample (strongest, weakest and typical of each type,
  spread over the window) gets the full craft review, while every post keeps its numbers and content coding.
