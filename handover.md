# Quickplay handover (Tuesday 27 October 2026, 23:30 UK)

Read this first, then CLAUDE.md (the rules and the index), then run `python pipeline/digest.py`. This is the full
handover; docs/HANDOVER.md is the short version.

## In short
Quickplay is a fully automated YouTube Shorts studio on the studio Google account (studiosocialmedia123@gmail.com).
GitHub Actions in quickplay-studio/quickplay-autopilot do everything, and nothing waits for a person. A Claude session is
only for changes Charlie asks for.

The goal (Charlie, 26 October; every change serves it): reach the YouTube Partner Programme, or find a clipping strategy
that makes real views and money.
- YPP counts engaged views (viewers who stay past the opening).
- Expanded tier: 500 subscribers and 3M Shorts views in 90 days.
- From 1 February 2027, full YPP needs 1,000 subscribers and 20M views (the Shorts pool 10M).
- Each change says which goal it helps and which number it should move; that number is its ledger target.

Links:
- Hub (Charlie's view, reads the live files): https://quickplay-studio.github.io/quickplay-autopilot/hub.html
- Repo: https://github.com/quickplay-studio/quickplay-autopilot
- Latest changes: CH-128 to CH-131, all on 27 October (below)

## State now
| | |
|---|---|
| Subscribers | 17 (500 for the expanded tier, 1,000 for full YPP) |
| Shorts views (90 days) | 10,213; about 111,000 a day needed for 10M |
| Last week (issue #48) | 131 Shorts, 26,061 views (489 the week before) |
| Uploads, last 24 hours | 23 of 40 YouTube uploads |
| Made | 23 Shorts for today, 7 so far for Wednesday 28 October |
| Volume test | 15 a day on main, day 3 of 14, judged from Sunday 8 November (status/volume.json). Early read: daily views 1.15x (interval 0.83 to 1.74); median 24-hour views a Short 68 against 18.5 before |
| Boards | queue 0, ready 1, done 184, failed 1, reserve 4, rejected 8, expired 4 |
| Keys (status/keys.json) | 14 ok, 12 missing; none of the missing ones blocks the main channel |

- Failed: QD-217 ("unclear narration in beat 0"). QD-086 and QD-126 are old and retired; digest.py still lists them from
  their old status files.
- Awaiting approval: QD-066, QD-144, QD-150, QD-160 (Ballon d'Or: most wins).
- Expired by the freshness gate: QD-213 and QD-218.
- The Ballon d'Or is at 92.84 times its usual searches. Under CH-131 that is the top mega tier: 10 Shorts a day on main
  plus up to 3 angles on the clips channel. The first 4 come from the 06:47 UTC breaking check on Wednesday
  28 October; the rest from the 08:10, 12:47 and 18:23 UTC runs.
- Open alert #50: retention is falling (viewers leave sooner than last week). The opening-first hook testing (CH-097)
  and subject-first pictures (CH-130) are the answer in progress; watch the engaged share on the hub.
- Missing keys: IG and FB tokens for the clips, gaming and irl channels; CEREBRAS_API_KEY, CF_API_TOKEN,
  MISTRAL_API_KEY, SAMBANOVA_API_KEY, APIFY_TOKEN, ANTHROPIC_API_KEY.
  - Mistral and Cloudflare are recommended: by the afternoon the four channels use up the strong free models, and the
    Lite fallback fails about 3 scripts in 8. A mega day writes more, so this matters more now.
  - Cerebras now needs a card, so it is not an option.

## Channels
| Channel (config key) | Posts | Per day |
|---|---|---|
| Quickplay Daily (main) | Original Shorts from what people search for | 15 in the volume test, plus mega Shorts on top |
| Quickplay Clips, Gaming Clips, IRL Clips (clips, gaming, irl) | Original Shorts on their own lanes; clipping paused | 6 each, plus up to 3 mega angles on a fitting channel |
| Quickplay Music (music) | Music Shorts | 6, waits until Charlie creates the channel (issue #42) |
| Quickplay Diario (es) | Spanish mirror on Americas slots | 6, waits until Charlie creates the channel (issue #43) |

- All YouTube channels share one allowance: 10,000 units, plus 100 uploads and 100 searches a day (quota.py).
- Instagram posts. Facebook runs a 1-a-day probe (Meta spam limit since 23 October, issue #34). TikTok is off
  (restricted 19 October, issue #35, docs/TIKTOK.md).
- Clipping: paused since 26 October (config.json clips_paused; set it to "" to clip again). Charlie decides whether it
  comes back; the review is Sunday 8 November (issue #49). Don't change clips_paused or campaigns.json youtube_off
  unless he asks.

## What was built in the last few days
- **27 October, CH-131: mega trends** (Charlie: big searches must be pushed hard, in real time).
  - 20, 50 or 90 times usual searches (or 500k Wikipedia views on a jump) give 5, 8 or 10 Shorts a day on momentum
    alone, ON TOP of quota.target().
  - Own slots (plan.with_mega, in the widest gaps); upload room (quota.uploads_left).
  - A fitting channel adds up to 3 angles; a breaking check writes 4 at once; a daily angle may run twice.
  - Six mega angles: people, rankings, numbers, moments, next, past.
  - It tapers to half its peak (at least 2) off the tiers, and ends under 3x or after 7 days.
  - Defaults in watch.VIRAL_DEFAULTS["mega"]; config.json viral.mega overrides them (no override set now).
  - Column mega. The volume test (analytics.volume_days) and the reserve leave mega Shorts out.
  - Test: tests/test_mega_trend.py. Ledger target yt_views_day.
- **27 October, CH-130: subject-first pictures** (fetch_media.rescue). An off-topic (relevance under 0.25) or missing
  picture is swapped for the beat's named subject's free Wikipedia lead or Commons photo when it scores better.
  config.json "pictures"; columns pic_low_share, pic_rescued; drivers pic_band. Never ceremony or broadcast footage.
  Target engaged_share.
- **27 October, CH-129: viral topics** (config.json "viral", watch.viral_items). A topic on 3+ free trend sources and
  rising gets extra places for up to 7 days, one angle a Short (latest, why, reaction, records, explained, facts),
  never event footage. Columns viral and viral_angle. The "🔥 ... is surging" issues are its notices.
- **27 October, CH-128: topic heat** (pipeline/heat.py). Every verdict (drivers, round, evolve, changes, trend, alerts,
  insights) separates a choice's effect from its topics' trend heat, so a Short riding a trending story is not credited
  to the change.
- **26 October, CH-096 to CH-098:**
  - CH-096: clip channels stay on original Shorts while clipping is paused.
  - CH-097: opening first. hook_type, first_frame, fx_opening and "opening" genes are judged on the engaged share (a win
    needs 10%, and a clear views loss withholds it). evolve.focus_first reopens an absent opening factor first; every
    opening_gene_every-th new gene is an opening gene. Engaged views lag about 3 days.
  - CH-098: the hub's improvement line (analytics/improvement.json, trend.history), each YPP number and per-Short
    metric by day.
- CH-099 to CH-127 are the Recipe's own changes dated 20 October that the analytics run added to the ledger; nothing to do.
- **26 October, CH-091 to CH-095:** original Shorts on all four channels (CH-091); one pooled, channel-aware learning
  model (CH-092); the missed-run watchdog, watchdog.yml hourly at :41 (CH-093); the self-evolving test round, evolve.yml
  daily at 07:23 UTC (CH-094); channel lanes (CH-095).
- **24 to 25 October:** keys.py live checks and actions.py (the hub's to-do list), the freshness gate, the change ledger,
  the negative-word rule, the 15-a-day volume test, the subscriber push in every Short (CH-082), round 1 started.

Full history: docs/NEXT.md, newest at the bottom.

## How the learning works
- Every Short is a test, with about 40 choices recorded per Short (category, hook, length, slot, look, writer model,
  heat, viral, mega, pictures and more).
- **analytics/drivers.csv (the older loop):** push or cut back only with proof.
  - The proof: 5 Shorts over 2 UK days, a 90% interval clear of typical, and both halves agreeing.
  - A choice with little to no views a week on is paused 14 days, then retested.
  - 1 Short in 5 explores, and every category keeps a floor.
  - No writer model passes 35% before 10 measured Shorts.
  - A dead Short is never remade.
- **analytics/round.csv (the pooled round):** 24-hour views over the same-UK-day median on the same channel, adjusted
  for channel, exploration, the other arms and topic heat. Opening factors use the engaged share instead. Verdicts:
  - **winner:** the interval is clear, 10+ Shorts a side, the effect is 0.14 or more (10% on the engaged share) and both
    halves agree;
  - **even:** the interval is within ±0.14, with 20+ Shorts;
  - **no clear difference:** 70 Shorts an arm reached with neither of the above;
  - **running** or **too few to tell:** not decided yet.
- **analytics/channel_drivers.csv:** a channel differs from the pool only with 10+ of its own Shorts proving it.
- **evolve.py:** keeps the round full (13 of 13 live now, including genes g003 and g004). State in
  analytics/evolve.json, log analytics/evolve_log.csv, summary analytics/evolve.md.
- **analytics/changes.csv:** the change ledger. Every pushed change has a row, and its verdict comes by itself after a week.
- **Other watchers:**
  - trend.py watches the absolute numbers week on week (analytics/insights.md, "Is the channel getting better").
  - alerts.py opens an issue when retention falls or the recipe stops refreshing (#50 is open now).
  - The Monday report is a GitHub issue labelled weekly.

## Open items
For the next Claude session:
1. Wednesday 28 October: check the Ballon d'Or mega push landed (4 Shorts from the 06:47 UTC breaking check, about 10
   over the day on main, up to 3 on clips) and that the volume test and reserve left them out.
2. Retention alert #50: watch the engaged share as CH-097 and CH-130 take effect (engaged views lag about 3 days).
3. QD-217 failed on unclear narration; the third such failure. If it repeats, look at the narration check or the voice.
4. tests/test_series.py section 12b still reads live data and fails (AssertionError at line 395, 'Sport Explained',
   'Science Explained'). It is not a code fault; making it hermetic is a small job.
5. Ledger verdicts for CH-128 to CH-131 arrive by themselves from about Tuesday 3 November; round and evolve
   settlements on the hub's test table; the volume test from Sunday 8 November.
6. The "🔥 ... is surging" issues (#29, #30, #32, #33, #39, #44, #47, #52 to #56) are notices only and pile up.
7. Clipping comes back only on Charlie's call (#49).

For Charlie (the hub's "Your actions this week", issues labelled needs-charlie):
1. Overdue (was due 27 October): check the Facebook Page for a restriction:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/34
2. By Wednesday 28 October: find out why TikTok restricted the account:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/35
3. By Sunday 8 November: keep clipping paused or restart it:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/49
4. Optional: create Quickplay Music (https://github.com/quickplay-studio/quickplay-autopilot/issues/42) and Quickplay
   Diario (https://github.com/quickplay-studio/quickplay-autopilot/issues/43).
5. By Thursday 10 December: renew IG_TOKEN: https://github.com/quickplay-studio/quickplay-autopilot/issues/36
6. Recommended free keys (one more writing model each): Mistral and Cloudflare. Optional: SambaNova.
   ANTHROPIC_API_KEY would take the pipeline's Claude calls off his chat allowance. A new key also goes on
   config.json accounts.secrets by hand, or the identity audit stops posting.

## Scheduled tasks (claude.ai)
- **Quickplay: Chrome jobs (on the Mac):**
  - runs every 2 hours from 09:07 to 23:07 UK, on Sonnet;
  - needs "Require this computer" on;
  - with clipping paused it mostly finds nothing and stops in under a minute.
- **Quickplay: weekly improvement review:** Mondays at 10:13 UK, on Sonnet. It follows docs/WEEKLY_REVIEW.md.
- **QUICKPLAY: ask:** fired from Charlie's pinned Quickplay page (the portal).
- Lodestone: console sync is a separate project. Do not touch it from here.

## Where to look
| What | Where |
|---|---|
| Rules and index | CLAUDE.md |
| State at a glance | `python pipeline/digest.py` (one screen); `python pipeline/health.py` |
| History | `tail -n 40 docs/NEXT.md`; clips history in docs/CLIPS.md |
| What works | analytics/insights.md (the Recipe), analytics/decisions.csv, drivers.csv, round.csv, channel_drivers.csv |
| Getting better? | analytics/improvement.json (the hub's improvement line) |
| The round's evolution | analytics/evolve.md (summary), evolve.json, evolve_log.csv |
| Did changes work | analytics/changes.csv, analytics/weekly.md |
| Viral and mega | config.json "viral" and "watchlist"; pipeline/watch.py |
| One Short | status/<id>.json |
| Logs | status/write_log.txt, status/factpack_log.txt (tail only) |
| Mac work | docs/CHROME_JOBS.md, `python3 pipeline/mac_rows.py`, docs/CHROME_LOG.md |
| Claude Code on the Mac | docs/CLAUDE_CODE.md |
| Haiku helpers | .claude/agents/: quickplay-logs, quickplay-data, quickplay-tests, quickplay-docs |

Token budget: Charlie's allowance is shared with other projects. Never open a data file whole (use head, tail, grep or a
one-line aggregate), and hand logs, numbers, tests and doc lines to the Haiku agents.

## Rules that never bend
- **Accounts and keys:**
  - Studio account and this repo only, never Charlie's personal accounts, email or files.
  - Never type passwords, codes or tokens, and never create accounts. Never list or read tokens/.
  - Keys go in GitHub secrets only. A new secret is added to config.json accounts.secrets by hand, or the identity audit
    stops posting.
  - Never route a Max OAuth token through a third party.
- **Ask Charlie first** before anything new that is public, any download to his computer or any purchase. Tools must be
  free; no paid tools until the channel earns.
- **Content:**
  - Anonymous and family friendly.
  - UK English ("Tuesday 20 October", colour, favourite).
  - No em or en dashes anywhere (in tests, write them as escapes).
  - Never politics, crime, health claims, money advice, adult content or gambling.
  - Never negative about a real person; negative turns only in fiction.
  - Never other creators' or broadcast footage without permission.
  - Nothing invented: every claim cites its source.
  - Weak Shorts stay up (a remake, never a delete).
  - A subscriber push is built into everything.
- **Supply chain:** every install uses pip 26.2.1 with `--uploaded-prior-to P7D`, and npm global installs use `--before`
  7 days ago. Pin exact versions where a package matters. No PHP.
- **Replies:** terse and conclusion first, with step-by-step lists that include every link. No recap messages.

## Making a change
1. Run `git pull`, read CLAUDE.md and run `python pipeline/digest.py`.
2. Make only the change asked for, and say which goal it serves and which number it should move. For a writer change,
   test it for real with "dry 2" in requests/write.txt.
3. Run all of tests/ (the quickplay-tests agent; `python3 tests/test_x.py`, pytest is not installed) and push only on a
   clean run. A for-loop over the tests does not fail the shell chain by itself. In tests, set shorts_channels to {}.
4. Add a ledger row: `python pipeline/changes.py add --area .. --change .. --hypothesis .. --target .. --guardrails ..`
5. Add one dated line to docs/NEXT.md (docs/CLIPS.md for clips work).
6. Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>, then `git pull --rebase` and push. The
   workflows push often, so retry the pull and push if the push is rejected. Never break the next scheduled run.
7. Check board shape with `python pipeline/validate.py boards/queue/<file>`. To make a new board, copy one from
   boards/done.
