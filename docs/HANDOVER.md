# Quickplay handover (Friday 30 October 2026)

> The short version. The full handover (state table, what was built, the learning model, open items, rules) is
> handover.md at the repo root.

Read CLAUDE.md, then run `python pipeline/digest.py`. Everything runs on GitHub; a Claude session is only for changes Charlie
asks for. Hub: the repo front page, https://github.com/quickplay-studio/quickplay-autopilot (README.md).

Goal: the YouTube Partner Programme (expanded tier 500 subscribers and 3M Shorts views in 90 days; from 1 February 2027,
1,000 and 20M, Shorts pool 10M), or a clipping strategy that makes real views and money.

## Resumed
GitHub Actions stopped on 28 October, 20:58 UTC: the repo was private, GitHub Free gives an organisation 2,000 private
Actions minutes a month, and the pipeline uses about 2,500 a day. Charlie made the repo public again on 30 October, so Actions
run free and resumed. The outage window (28 October 20:58 UTC until the restart) must be left out of the verdicts. The browser
hub reads raw files with no token again; Pages was unpublished while private and needs switching on at
https://github.com/quickplay-studio/quickplay-autopilot/settings/pages (Deploy from a branch, main, /docs).

## State (data stops 28 October, 20:50 UTC)
- 19 subscribers; engaged views 1,243 a day (7-day average), up from 505 a week earlier; about 33,200 a day needed.
- Volume test day 4 of 14, judged from 8 November (1.11x daily views so far); the outage must be left out of it.
- Four channels write original Shorts; clipping paused (review 8 November, #49). Facebook probe (#34), TikTok off (#35).
- Change pause until the verdicts: a one-off scheduled task on Sunday 8 November, 19:37 UK, reads them and builds the
  breakout target and the YPP readiness check.

## Built 27 and 28 October
- CH-132 FreeLLMAPI router (Kilo and OVH models, fails open; search needs a key).
- CH-153 private-repo page sync (undone 30 October: the hub is public and token-free again), CH-154 README hub.
- CH-155 sameness guard, CH-156 frozen control (1 in 10).
- CH-157 luck check (Benjamini-Hochberg) and re-test before lock-in, CH-158 views_7d, subscribers by day, feed share,
  CH-159 joint model.

## Open
- Restart checks now Actions has resumed; the outage inside the volume test and ledger windows; near-duplicate mega
  titles (QD-253, QD-255); render "Upload to YouTube" failures (20 of 30 before the outage); Instagram failures
  QD-189, QD-209, QD-227; known failing tests (soundfile, series, channels, quota_buckets, volume; watch depends on the date).
- For Charlie: switch Pages on again (above); Facebook (#34) and TikTok (#35), both overdue; Mistral, Cloudflare and Tavily keys;
  clipping decision by 8 November (#49); IG_TOKEN by 10 December (#36); optional Music and Diario (#42, #43).

## Rules
CLAUDE.md "Channel rules" and "Working rules". Run every test before a push and push only on a clean run apart from the
known failures. Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>.
