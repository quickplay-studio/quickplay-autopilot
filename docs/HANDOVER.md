# Quickplay handover (Tuesday 27 October 2026, 23:30 UK)

> The short version. The full handover (state table, channels, the learning model, open items, rules) is handover.md at
> the repo root.

Read CLAUDE.md, then run `python pipeline/digest.py`. Everything runs on GitHub; a Claude session is only for changes Charlie
asks for. Hub: https://quickplay-studio.github.io/quickplay-autopilot/hub.html

Goal: the YouTube Partner Programme (expanded tier 500 subscribers and 3M Shorts views in 90 days; from 1 February 2027,
1,000 and 20M, Shorts pool 10M), or a clipping strategy that makes real views and money.

## State
- 17 subscribers; 10,213 Shorts views (90 days). 23 of 40 uploads in 24 hours.
- Volume test 15 a day on main, day 3 of 14, judged from 8 November (status/volume.json); early read 1.15x daily views.
- Four channels write original Shorts (main 15 a day, gaming, irl, clips 6 each); clipping paused (config clips_paused,
  review 8 November, #49). Music and Spanish channels wait on Charlie (#42, #43). Facebook 1-a-day probe (#34), TikTok
  off (#35).
- The Ballon d'Or is at 92.84x usual searches: the top mega tier, 10 Shorts a day on main plus up to 3 on clips, from
  the 06:47 UTC breaking check on 28 October.
- Alert #50: retention falling. QD-217 failed on unclear narration.

## Built 27 October
- **CH-128 topic heat** (heat.py): every verdict separates a choice's effect from its topics' trend heat.
- **CH-129 viral topics** (watch.viral_items): 3+ free trend sources and rising gives extra places for up to 7 days.
- **CH-130 subject-first pictures** (fetch_media.rescue): off-topic or missing pictures swapped for the named subject's
  free Wikipedia or Commons photo. Never ceremony or broadcast footage.
- **CH-131 mega trends:** 20, 50 or 90x usual searches give 5, 8 or 10 Shorts a day on top of quota.target(), own slots
  and upload room, up to 3 angles on a fitting channel, 4 at once from a breaking check, taper to half, end under 3x or
  after 7 days. Test: tests/test_mega_trend.py.
- 26 October: CH-096 (clip channels on original Shorts), CH-097 (hook tests on the engaged share), CH-098 (the hub's
  improvement line); CH-091 to CH-095 (all four channels, pooled model, watchdog, self-evolving round, channel lanes).

## Open
- Watch the Ballon d'Or mega push on 28 October; the engaged share for #50; ledger verdicts for CH-128 to CH-131 from
  about 3 November; the volume test from 8 November.
- tests/test_series.py section 12b reads live data and fails (line 395); not a code fault.
- For Charlie (hub, "Your actions this week"): Facebook restriction check (#34, overdue); TikTok reason by 28 October
  (#35); clipping decision by 8 November (#49); Mistral and Cloudflare keys; IG_TOKEN by 10 December (#36); optional
  Music and Diario channels (#42, #43).

## Rules
CLAUDE.md "Channel rules" and "Working rules". Run every test before a push and push only on a clean run (a for-loop over
the tests does not fail the shell chain by itself). Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>.
