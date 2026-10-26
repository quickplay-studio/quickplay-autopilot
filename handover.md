# Quickplay handover (Monday 26 October 2026, 15:45 UK)

Read this first, then CLAUDE.md (the rules and the index), then run `python pipeline/digest.py`. This is the full
handover; docs/HANDOVER.md is the short version.

## In short
Quickplay is a fully automated YouTube Shorts studio on the studio Google account (studiosocialmedia123@gmail.com).
GitHub Actions in quickplay-studio/quickplay-autopilot do everything, and nothing waits for a person. The goal is the
YouTube Partner Program: 1,000 subscribers and 10M Shorts views in 90 days, applied for before 1 February 2027. A Claude
session is only for changes Charlie asks for.

- Hub (Charlie's view, reads the live files): https://quickplay-studio.github.io/quickplay-autopilot/hub.html
- Repo: https://github.com/quickplay-studio/quickplay-autopilot
- Latest changes: CH-092 to CH-095, all on 26 October (below)

## State now
| | |
|---|---|
| Subscribers | 16 of 1,000 |
| Shorts views (90 days) | 7,789 of 10M, about 111,000 a day needed |
| Last week (issue #48) | 131 Shorts, 26,061 views (489 the week before) |
| Following the data | Shorts that followed the rulings: median 92 views against 18 for the rest (5.1x) |
| Uploads, last 24 hours | 18 of 40 YouTube uploads |
| Volume test | 15 a day, day 2 of 14, judged from Sunday 8 November (status/volume.json); early read: daily views 1.31x, interval 0.98 to 1.88 |
| Boards | queue 0, ready 1, done 150, failed 0, reserve 3, rejected 8, expired 2 |
| Keys (status/keys.json) | 14 ok, 12 missing; none of the missing ones blocks the main channel |

- The 3 failed boards are retired: QD-126 expired; QD-051 and QD-086 rejected. digest.py still lists QD-086 and QD-126
  under "needs attention" from their old status files; nothing to do.
- Awaiting approval: QD-066, QD-144, QD-150, QD-160.
- Breakouts (the breakout follow-up, CH-001, handles these by itself): QD-165 Song Secrets #1 Shakira (247x typical at
  24 hours), QD-164 GTA 6 price (67.7x), QD-159 Free Steam games Part 2 (64x).
- Missing keys: IG and FB tokens for the clips, gaming and irl channels; CEREBRAS_API_KEY, CF_API_TOKEN,
  MISTRAL_API_KEY, SAMBANOVA_API_KEY, APIFY_TOKEN, ANTHROPIC_API_KEY.
  - Mistral and Cloudflare are now recommended: by the afternoon the four channels use up the strong free models, and
    the Lite fallback fails about 3 scripts in 8.
  - Cerebras now needs a card, so it is not an option.

## Channels
| Channel (config key) | Posts | Per day |
|---|---|---|
| Quickplay Daily (main) | Original Shorts from what people search for | 15 in the volume test |
| Quickplay Clips, Gaming Clips, IRL Clips (clips, gaming, irl) | Original Shorts on their own lanes since 26 October; clipping paused | 6 each |
| Quickplay Music (music) | Music Shorts | 6, waits until Charlie creates the channel (issue #42) |
| Quickplay Diario (es) | Spanish mirror on Americas slots | 6, waits until Charlie creates the channel (issue #43) |

- All YouTube channels share one allowance: 10,000 units, plus 100 uploads and 100 searches a day (quota.py).
- Instagram posts. Facebook runs a 1-a-day probe (Meta spam limit since 23 October, issue #34). TikTok is off
  (restricted 19 October, issue #35, docs/TIKTOK.md).
- Clipping: paused since 26 October (config.json clips_paused). Set it to "" to clip again. Charlie's plan is to go back
  to clipping once the channels have traction. The clip stop rule had already stopped YouTube clip uploads on gaming
  and clips (issues #45, #46); those issues are moot while clipping is paused.

## What was built in the last few days
- **26 October, CH-095: channel lanes.** writer.evergreen_packs(lane=brief) tells the plan the channel's lane and drops
  ideas outside its categories. The first all-channel write (QD-191 to QD-194) uploaded to the right channels, but
  QD-191 (films on gaming) and QD-193 (games on irl) were off their lanes; CH-095 stops that from the next run.
- **26 October, CH-094: the self-evolving test round** (pipeline/evolve.py, evolve.yml daily at 07:23 UTC).
  - It retires settled contests (a winner becomes a champion) and opens up to 3 new contests a day, up to 13 at once.
  - New contests come from four sources, picked by Thompson sampling on each source's own win record:
    - neighbour: an untried arm against the champion;
    - retest: a settled contest again after 28 days;
    - gene: a writing instruction, tested against none;
    - mutate: a refinement of an adopted gene, against its parent.
  - Claude Opus proposes genes (one call a run; the free models are only the fallback). Charlie, 26 October: complex
    steps on Claude, day to day on free models.
  - A proposal must work alongside every arm under test. g001 and g002 restated the hook test and were retired unused;
    g003 (compare the first number to something familiar) is live.
  - Switch off with config.json evolve.on false.
- **26 October, CH-093: the missed-run watchdog** (pipeline/watchdog.py, watchdog.yml hourly at :41). GitHub dropped the
  12:47 UTC trends run that day.
  - It starts trends when a main slot (08:10, 12:47, 18:23 UTC) has no run 50 minutes on.
  - It restarts render, analytics, social, engage or evolve when one is past its gap.
  - publish.yml is left out, because a manual dispatch defaults to "approve all".
- **26 October, CH-092 (b7bd2bf): one pooled, channel-aware learning model.** Every channel's Shorts feed one test round.
  - The measure is 24-hour views over the same-UK-day median on the same channel, so channels of different sizes compare
    fairly.
  - analytics/round.csv gives verdicts adjusted for channel, exploration and the other arms (pipeline/drivers.py,
    round_verdicts).
  - analytics/channel_drivers.csv lets a channel differ from the pool only with 10+ of its own Shorts proving it
    (channel_table).
  - The writer: drivers.csv push rows first, round.csv winners override them, then channel exceptions (not on main).
    Settled factors leave the round; the first Short of each channel's day explores (pipeline/writer.py).
  - The hub's test table has a "Result so far" column. Test: tests/test_one_model.py.
- **26 October, CH-091 (0900a55):** original Shorts on all four channels through shorts_channels; clipping paused.
- **25 to 26 October:**
  - The Mac Chrome task needs "Require this computer" switched on in the Claude desktop app, or it runs in the cloud with
    no browser.
  - Music and Spanish channels approved; they wait on Charlie creating them.
  - Subscriber push built into every Short (CH-082).
  - Commentary Shorts for clips (CH-083).
  - Round 1 started on 25 October.
- **24 October:**
  - keys.py live checks and actions.py, which keeps the hub's to-do list true.
  - The freshness gate.
  - The change ledger.
  - The negative-word rule, with the game_shows exception.
  - The 15-a-day volume test.

Full history: docs/NEXT.md, newest at the bottom.

## How the learning works
- Every Short is a test, with about 40 choices recorded per Short (category, hook, length, slot, look, writer model and
  more).
- **analytics/drivers.csv (the older loop):** push or cut back only with proof.
  - The proof: 5 Shorts over 2 UK days, a 90% interval clear of typical, and both halves agreeing.
  - A choice with little to no views a week on is paused 14 days, then retested.
  - 1 Short in 5 explores, and every category keeps a floor.
  - No writer model passes 35% before 10 measured Shorts.
  - A dead Short is never remade.
- **analytics/round.csv (round 1):** 11 factors, 70 Shorts an arm (config.json test_round). The factors are hook_type,
  length, title_search, first_frame, fx_energy, fx_slot, fx_grade, fx_opening, ending, angles and franchise. "lab" means
  the newest active lab look. Each factor gets one of these verdicts:
  - **winner:** the interval is clear, there are 10+ Shorts a side, the effect is 0.14 or more and both halves agree;
  - **even:** the interval is within ±0.14, with 20+ Shorts;
  - **no clear difference:** 70 Shorts an arm reached with neither of the above;
  - **running** or **too few to tell:** not decided yet.
- **evolve.py (CH-094):** keeps the round full by itself, as above. State in analytics/evolve.json, log in
  analytics/evolve_log.csv, summary in analytics/evolve.md.
- **analytics/changes.csv:** the change ledger. Every pushed change has a row, and its verdict comes by itself after a week.
- **Other watchers:**
  - trend.py watches the absolute numbers week on week (analytics/insights.md, "Is the channel getting better").
  - alerts.py opens an issue when retention falls or the recipe stops refreshing.
  - The Monday report is a GitHub issue labelled weekly.

## Open items
For the next Claude session:
1. Check that the next all-channel write keeps each channel on its lane (CH-095).
2. Watch round 1 verdicts and evolve's first settlements land (analytics/round.csv, analytics/evolve.md, the hub's
   "Result so far").
3. The volume test verdict comes from Sunday 8 November.
4. Clipping comes back only when Charlie decides the channels have traction.

For Charlie (the hub's "Your actions this week", issues labelled needs-charlie):
1. By Tuesday 27 October: check the Facebook Page for a restriction:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/34
2. By Wednesday 28 October: find out why TikTok restricted the account:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/35
3. Optional: create Quickplay Music (https://github.com/quickplay-studio/quickplay-autopilot/issues/42) and Quickplay
   Diario (https://github.com/quickplay-studio/quickplay-autopilot/issues/43).
4. By Thursday 10 December: renew IG_TOKEN: https://github.com/quickplay-studio/quickplay-autopilot/issues/36
5. Recommended free keys (one more writing model each): Mistral and Cloudflare. Optional: SambaNova.
   ANTHROPIC_API_KEY would take the pipeline's Claude calls off his chat allowance.
6. Issues #45 and #46 (clip stop rule) can be closed while clipping is paused.

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
| The round's evolution | analytics/evolve.md (summary), evolve.json, evolve_log.csv |
| Did changes work | analytics/changes.csv, analytics/weekly.md |
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
  - Never type passwords, codes or tokens, and never create accounts.
  - Keys go in GitHub secrets only. A new secret is added to config.json accounts.secrets by hand, or the identity audit
    stops posting.
  - Never route a Max OAuth token through a third party.
- **Ask Charlie first** before anything new that is public, any download to his computer or any purchase. Tools must be
  free; no paid tools until the channel earns.
- **Content:**
  - Anonymous and family friendly.
  - UK English ("Tuesday 20 October", colour, favourite).
  - No em or en dashes anywhere.
  - Never politics, crime, health claims, money advice, adult content or gambling.
  - Never negative about a real person; negative turns only in fiction.
  - Never other creators' footage without their permission.
  - Nothing invented: every claim cites its source.
  - Weak Shorts stay up (a remake, never a delete).
  - A subscriber push is built into everything.
- **Supply chain:** every install uses pip 26.2.1 with `--uploaded-prior-to P7D`, and npm global installs use `--before`
  7 days ago. Pin exact versions where a package matters. No PHP.
- **Replies:** terse and conclusion first, with step-by-step lists that include every link. No recap messages.

## Making a change
1. Run `git pull`, read CLAUDE.md and run `python pipeline/digest.py`.
2. Make only the change asked for. For a writer change, test it for real with "dry 2" in requests/write.txt.
3. Run all of tests/ (the quickplay-tests agent) and push only on a clean run. A for-loop over the tests does not fail
   the shell chain by itself.
4. Add a ledger row: `python pipeline/changes.py add --area .. --change .. --hypothesis .. --target .. --guardrails ..`
5. Add one dated line to docs/NEXT.md (docs/CLIPS.md for clips work).
6. Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>, then `git pull --rebase` and push.
   Never break the next scheduled run.
7. Check board shape with `python pipeline/validate.py boards/queue/<file>`. To make a new board, copy one from
   boards/done.
