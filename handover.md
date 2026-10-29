# Quickplay handover (Thursday 29 October 2026, 18:30 UK)

Read this first, then CLAUDE.md (the rules and the index), then run `python pipeline/digest.py`. This is the full
handover; docs/HANDOVER.md is the short version.

## STOPPED: GitHub Actions has not run since 28 October, 20:58 UTC
- Every workflow since then ends "failure" with 0 steps. The annotation reads: "The job was not started because recent
  account payments have failed or your spending limit needs to be increased."
- Cause: the repo was made private on 27 or 28 October. GitHub Free for organisations includes 2,000 Actions minutes a
  month for private repos; Actions on public repos are free. The pipeline uses roughly 2,500 or more minutes a day
  (about 389 runs between 27 October 18:00 and 28 October 21:00 UTC), so the month's allowance went in under a day.
  The FreeLLMAPI step and three 50-minute dry write runs on 28 October added to it.
- Effect: no uploads, posts, analytics, trends, writing or audits since then; the last data commit is "Hourly numbers
  2026-10-28 20:50". Digest shows 0 of 40 YouTube uploads in 24 hours.
- Fix (Charlie's call; a session cannot change repo visibility or billing):
  - Recommended, free: make the repo public again at https://github.com/quickplay-studio/quickplay-autopilot/settings
    (Danger Zone, Change visibility, Public). Then check https://github.com/quickplay-studio/quickplay-autopilot/settings/pages
    is "Deploy from a branch", main, /docs, so the browser hub comes back too.
  - Staying private means a card and a spending limit (against the free-only rule) at
    https://github.com/organizations/quickplay-studio/settings/billing. Not recommended.
- Once runs start again: check the next runs succeed, uploads resume, README.md rebuilds hourly and the key check runs.
  Stale time-sensitive boards scheduled for 28 and 29 October will expire through the freshness gate (expected).
- If the repo goes public: docs/hub.html now reads through the contents API with a token. Unauthenticated, the API
  allows 60 requests an hour per address, so either paste a read-only token in the hub or switch its reads back to
  raw.githubusercontent.com (a small job). The private-hub sync (pages.yml, pages_sync.py, HUB_PUSH_TOKEN) is then
  optional; it does nothing until the secret and the public org-site repo exist.

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

Change pause (Charlie agreed, 28 October): no new builds until the verdicts arrive. A one-off scheduled task on
Sunday 8 November at 19:37 UK reads them and builds the two queued changes (below).

Links:
- Hub inside GitHub (README.md, rebuilt hourly when Actions runs): https://github.com/quickplay-studio/quickplay-autopilot
- Browser hub (offline while the repo is private): https://quickplay-studio.github.io/quickplay-autopilot/hub.html
- Latest changes: CH-132 and CH-153 to CH-159, 27 and 28 October (below)

## State (data stops at 28 October, 20:50 UTC)
| | |
|---|---|
| Subscribers | 19 (500 for the expanded tier, 1,000 for full YPP) |
| Shorts views (90 days) | 11,291 in digest; the hub's engaged figure was 12,422 on 28 October |
| Engaged views a day | 7-day average 1,243 on 28 October, up from 505 a week earlier; about 33,200 a day needed for 3M |
| Uploads, last 24 hours | 0 of 40 (the outage) |
| Volume test | 15 a day on main, day 4 of 14, judged from Sunday 8 November. Read on 28 October: daily views 1.11x (interval 0.79 to 1.64); median 24-hour views a Short 56 against 25 before. The outage days must be left out of its verdict |
| Boards | queue 3, ready 12, done 206, failed 3, reserve 4, rejected 8, expired 5 |
| Keys (status/keys.json) | 15 ok, 19 missing (all optional or channel tokens; none blocks the main channel) |
| FreeLLMAPI router | live on its last run: Kilo and OVH, 26 models, 37 calls served; no web search (needs a search key) |
| Sameness | main 0.06 (alert at 0.20); commonest recipe 4% (cap 35%) |
| Loop vs frozen control | too few to tell (0 control Shorts public yet) |

- Failed: QD-217, QD-240, QD-241 (QD-217 on unclear narration, the third such failure). QD-086 and QD-126 are old and
  retired; digest.py still lists them.
- Instagram post failures: QD-189, QD-209, QD-227.
- Awaiting approval: QD-066, QD-144, QD-150, QD-160 and newer (QD-229 onwards, see digest).
- Mega pushes on 28 October wrote many Shorts on two stories: Harry Kane's Ballon d'Or (about 7) and the death of Star
  Trek actor Walter Koenig (about 12). Several titles are near copies (QD-253 and QD-255: "the audition secret you
  missed/never knew"). Check that the sameness pair check bites on mega Shorts (open item 3).
- Open alert #50: retention falling. CH-097 (opening-first hooks) and CH-130 (subject-first pictures) are the answer
  in progress.
- Missing keys that matter: MISTRAL_API_KEY, CF_ACCOUNT_ID and CF_API_TOKEN (writing stalls in the afternoon),
  TAVILY_API_KEY (web search for fact packs). Cerebras and Brave need a card: not options.

## Channels
| Channel (config key) | Posts | Per day |
|---|---|---|
| Quickplay Daily (main) | Original Shorts from what people search for | 15 in the volume test, plus mega Shorts on top |
| Quickplay Clips, Gaming Clips, IRL Clips (clips, gaming, irl) | Original Shorts on their own lanes; clipping paused | 6 each, plus up to 3 mega angles on a fitting channel |
| Quickplay Music (music) | Music Shorts | 6, waits until Charlie creates the channel (issue #42) |
| Quickplay Diario (es) | Spanish mirror on Americas slots | 6, waits until Charlie creates the channel (issue #43) |

- All YouTube channels share one allowance: 10,000 units, plus 100 uploads and 100 searches a day (quota.py).
- Instagram posts. Facebook runs a 1-a-day probe (issue #34). TikTok is off (restricted 19 October, issue #35).
- Clipping: paused since 26 October (config.json clips_paused). Charlie decides on Sunday 8 November (issue #49), on
  money per week. Don't change clips_paused or campaigns.json youtube_off unless he asks.

## What was built 27 and 28 October
- **CH-132, FreeLLMAPI router** (pipeline/freellm.py, .github/actions/freellm in trends, write and evolve):
  - ghcr.io/tashfeenahmed/freellmapi:v0.16.6, pinned with its digest in config.json "freellm"; starts per run on the
    runner, fails open (a failure leaves the pipeline exactly as before).
  - Adds its top models and "freellm:auto" through factpack's one door; the writer label is the real model from
    X-Routed-Via (for example freellm:ovh/Mistral-Small-3.2-24B-Instruct-2506), so the learning judges each model.
  - Keyless: Kilo and OVH chat. v0.16.6 has no keyless search (Keenable is dropped at start), so web search needs
    TAVILY_API_KEY, EXA_API_KEY, FIRECRAWL_API_KEY or LINKUP_API_KEY. OLLAMA_API_KEY and LLM7_API_KEY are optional.
  - Never passed to the router: Gemini, Groq, OpenRouter, Mistral, Cloudflare, SambaNova, Cerebras, Claude keys.
  - Not enabled: Cohere (terms forbid), NVIDIA (evaluation only), AI Horde (volunteer commons). GitHub Models retired.
  - status/freellm.json; freellm.yml is a 2-minute check (push requests/freellm.txt). Test: tests/test_freellm.py.
- **CH-153, private-repo hub** (pages.yml, pipeline/pages_sync.py): copies docs/*.html and their assets only, never data,
  to the public repo quickplay-studio/quickplay-studio.github.io (folder quickplay-autopilot/) with HUB_PUSH_TOKEN; the
  hub reads the repo with a read-only token in the browser. Dormant: Charlie has not made the org-site repo or the secret.
- **CH-154, the hub inside GitHub:** README.md is the hub (pipeline/hub_md.py), rebuilt in the analytics.yml commit and
  after the audit's key check. The old README is docs/HOW_IT_WORKS.md. Test: tests/test_hub_md.py.
- **CH-155, sameness guard** (pipeline/sameness.py): each board is scored against the channel's last 14 days (narration,
  title pattern, opening, look, voice, format, series). Over max_pair 0.30 (the 97th percentile on boards/done) it is
  rewritten once, then dropped; no recipe over 35% of a channel's window (mega and the reserve exempt from the cap only).
  Columns sameness, sameness_recipe_share; analytics/sameness.csv and .md; ledger metric sameness, a default guardrail
  on every change; alert at 0.20 for 2 days. The dry run rewrote one draft from 0.30 to 0.21.
- **CH-156, frozen control:** 1 normal Short in 10 (its own seeded draw) is written with the recipe frozen on
  28 October (analytics/control_recipe.json), takes no test arm, gene or exploration, and is left out of every verdict.
  trend.py reports "Loop vs frozen control" (paired same-day ratios, heat adjusted, 90% interval). Needs 8 control
  Shorts over 3 days. Not yet seen in a real run (the dry run's 2 boards drew none).
- **CH-157, luck check and re-test** (pipeline/fdr.py): every verdict pass applies Benjamini-Hochberg at
  config analysis.fdr_q 0.10 (p and q in the CSVs; "running (luck check)"). On 28 October it downgraded 20 of 25 drivers
  push or cut rulings and 1 round winner (replies). Adopted round and evolve winners are "confirming" (confirm_share 0.2
  keep the old choice until confirm_n 20 a side), then locked in or reverted. Drivers pushes are not re-tested (skipped).
- **CH-158, better targets:** views_7d and views_28d (from the hourly curves, 0 API units; 60 Shorts so far);
  analytics/subs_daily.csv and subs_model.md (channel-day subscriber model, needs 20 channel-days, had 10); ledger
  metrics feed_share, views_7d_median, subs_day; yt_feed_pct in drivers' outcome table.
- **CH-159, joint model** (pipeline/joint.py, analytics.yml): one shrunk regression of every factor, channel, heat and
  weekday, plus category interactions; analytics/joint.csv and joint.md. It can withhold a winner it clearly disagrees
  with and propose one category gene ("joint" source). Planted tests: a 1.65x effect recovered as 1.71x; a 2.46x
  interaction as 1.52x (shrinkage, the cautious side).
- 27 October, CH-128 to CH-131 (heat, viral topics, subject-first pictures, mega trends) and earlier: see docs/NEXT.md.

## How the learning works
- Every Short is a test, with about 40 choices recorded (analytics/shorts.csv has 121 columns).
- Drivers (analytics/drivers.csv): push or cut back only with proof (5 Shorts over 2 UK days, a 90% interval clear of
  typical, both halves agreeing) and now the luck check. 1 Short in 5 explores; every category keeps a floor; no writer
  model passes 35% before 10 measured Shorts; a dead Short is never remade.
- The pooled round (analytics/round.csv): 24-hour views over the same-UK-day channel median, adjusted for channel,
  exploration, the other arms and heat; opening factors on the engaged share. Verdicts: winner (also passes the luck
  check, then confirming), even, no clear difference, running, too few to tell.
- channel_drivers.csv: a channel differs from the pool only with 10+ of its own Shorts.
- evolve.py (07:23 UTC): keeps the round full by Thompson sampling; one Claude (Opus) proposal call a run.
- Control Shorts and the joint model as above; changes.csv is the ledger (verdicts come by themselves after a week).
- Sample sizes are small: median 24-hour views about 27, median engaged views about 12, and 170 of 184 measured Shorts
  gained no subscribers. The top 10% of main-channel Shorts bring 41% of its views. Views, not subscribers, are the gate:
  at about 0.4 subscribers per 1,000 views, 3M views would bring about 1,200 subscribers.

## Open items
For the next Claude session:
1. After Actions is back: confirm the next runs succeed, uploads resume, README.md rebuilds and the key check runs.
2. The outage (28 October 20:58 UTC until restart) sits inside the volume test, the ledger windows and the control
   comparison. Make sure they leave it out, or say so; the 8 November task should account for it.
3. Mega pushes: near-identical titles on one story (QD-253 and QD-255). Check the sameness pair check on mega Shorts
   and whether 12 Shorts on one death is too many.
4. render.yml: 20 of 30 runs from 26 October to 28 October 19:00 ended "failure" at "Upload to YouTube" (before the
   outage). Check whether that is the learned upload ceiling working as designed or a fault.
5. Instagram post failures QD-189, QD-209, QD-227; QD-217, QD-240, QD-241 failed (narration check: a third unclear
   narration failure, look at the check or the voice if it repeats).
6. Tests that fail for reasons outside the code: seven that import soundfile (not installed in cloud sessions),
   test_series.py 12b, test_channels.py, test_quota_buckets.py, test_volume.py (live upload ceiling). test_watch.py
   failed on 28 October and passed on 29 October, so it depends on the date. Making them hermetic is a small job.
7. FreeLLMAPI: bump the pinned image when a release at least 7 days old supports Keenable or Parallel keyless search.
8. The "🔥 ... is surging" issues are notices only and pile up.
9. Session notes: job logs cannot be fetched from a cloud session (the log host returns 403), so diagnostics go into
   status files; a dry write run takes about 50 minutes; local test runs bump status/claude_usage.json, never commit it.

Queued (one-off scheduled task, Sunday 8 November, 19:37 UK, Opus deciding, Sonnet building):
- Read the verdicts (ledger from CH-128, volume test, loop vs control, luck checks, joint model); report anything hurting.
- Breakout target: a breakout outcome (calibrated so roughly the top 5% to 10% count) as a second score in round,
  drivers, joint and evolve; ledger metric breakout_share; a hub line.
- YPP readiness check in the Monday review: 10 recent Shorts per channel against YouTube's inauthentic content wording,
  analytics/ypp_readiness.md, a needs-charlie issue only if the channel would likely fail.

For Charlie:
1. Now: get Actions running again (see the top). Making the repo public is free.
2. Overdue: check the Facebook Page for a restriction: https://github.com/quickplay-studio/quickplay-autopilot/issues/34
3. Overdue (was due 28 October): find out why TikTok restricted the account:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/35
4. Free keys, added at https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new:
   MISTRAL_API_KEY (https://console.mistral.ai/api-keys), CF_ACCOUNT_ID and CF_API_TOKEN
   (https://dash.cloudflare.com/profile/api-tokens, Workers AI permission), TAVILY_API_KEY (https://app.tavily.com).
   Optional: SAMBANOVA_API_KEY, FIRECRAWL_API_KEY, EXA_API_KEY, LINKUP_API_KEY. All are already on config.json
   accounts.secrets. Skip any sign-up that asks for a card.
5. By Sunday 8 November: keep clipping paused or restart it, judged on money per week:
   https://github.com/quickplay-studio/quickplay-autopilot/issues/49
6. By Thursday 10 December: renew IG_TOKEN: https://github.com/quickplay-studio/quickplay-autopilot/issues/36
7. Optional: create Quickplay Music (#42) and Quickplay Diario (#43).
8. Pending his word: scheduled task models (move Lodestone console sync to Sonnet, the weekly review to Opus).

## Scheduled tasks (claude.ai)
| Task | When | Model |
|---|---|---|
| Quickplay: Chrome jobs (on the Mac) | every 2 hours, 09:07 to 23:07 UK; needs "Require this computer" | Sonnet |
| Quickplay: weekly improvement review | Mondays 10:13 UK, follows docs/WEEKLY_REVIEW.md | Sonnet (Opus recommended) |
| QUICKPLAY: ask | fired from Charlie's pinned Quickplay page | Sonnet |
| Quickplay: breakout target and YPP readiness (8 Nov build) | once, Sunday 8 November 19:37 UK | Opus |
| Lodestone: console sync | daily 08:10 UK; a separate project, do not touch it from here | Opus since 28 October (Sonnet recommended) |

## Where to look
| What | Where |
|---|---|
| Rules and index | CLAUDE.md |
| State at a glance | `python pipeline/digest.py` (one screen); `python pipeline/health.py`; README.md (the hub) |
| History | `tail -n 40 docs/NEXT.md`; clips history in docs/CLIPS.md |
| What works | analytics/insights.md, decisions.csv, drivers.csv, round.csv, channel_drivers.csv, joint.md |
| Getting better? | analytics/improvement.json ("Loop vs frozen control" too) |
| Sameness | analytics/sameness.md, sameness.csv |
| Subscribers | analytics/subs_daily.csv, subs_model.md |
| The round's evolution | analytics/evolve.md, evolve.json, evolve_log.csv |
| Did changes work | analytics/changes.csv, analytics/weekly.md |
| Router | status/freellm.json, pipeline/freellm.py |
| Viral and mega | config.json "viral" and "watchlist"; pipeline/watch.py |
| One Short | status/<id>.json |
| Logs | status/write_log.txt, status/factpack_log.txt (tail only) |
| Mac work | docs/CHROME_JOBS.md, `python3 pipeline/mac_rows.py`, docs/CHROME_LOG.md |
| Haiku helpers | .claude/agents/: quickplay-logs, quickplay-data, quickplay-tests, quickplay-docs |

Token budget: Charlie's allowance is shared with other projects. Never open a data file whole (use head, tail, grep or a
one-line aggregate), and hand logs, numbers, tests and doc lines to the Haiku agents.

## Rules that never bend
- **Accounts and keys:**
  - Studio account and this repo only, never Charlie's personal accounts, email or files.
  - Never type passwords, codes or tokens, and never create accounts. Never list or read tokens/.
  - Keys go in GitHub secrets only. A new secret is added to config.json accounts.secrets by hand, or the identity audit
    stops posting.
  - Never route a Max OAuth token or any Claude key through a third party (FreeLLMAPI included).
- **Ask Charlie first** before anything new that is public, any download to his computer or any purchase. Tools must be
  free; no paid tools until the channel earns. Repo visibility and billing are his call.
- **Content:**
  - Anonymous and family friendly.
  - UK English ("Thursday 29 October", colour, favourite).
  - No em or en dashes anywhere (in tests, write them as escapes).
  - Never politics, crime, health claims, money advice, adult content or gambling.
  - Never negative about a real person; negative turns only in fiction.
  - Never other creators' or broadcast footage without permission.
  - Nothing invented: every claim cites its source.
  - Weak Shorts stay up (a remake, never a delete).
  - A subscriber push is built into everything.
- **Supply chain:** every install uses pip 26.2.1 with `--uploaded-prior-to P7D`, npm global installs use `--before`
  7 days ago, and Docker images are pinned to a release at least 7 days old with its digest. No PHP.
- **Replies:** terse and conclusion first, with step-by-step lists that include every link. No recap messages.

## Making a change
1. Run `git pull`, read CLAUDE.md and run `python pipeline/digest.py`.
2. Make only the change asked for, and say which goal it serves and which number it should move. For a writer change,
   test it for real with "dry 2" in requests/write.txt (about 50 minutes; it uses Actions minutes).
3. Run all of tests/ (the quickplay-tests agent; `python3 tests/test_x.py`, pytest is not installed) and push only on a
   clean run apart from the known failures above. In tests, set shorts_channels to {}.
4. Add a ledger row: `python pipeline/changes.py add --area .. --change .. --hypothesis .. --target .. --guardrails ..`
   (`python pipeline/changes.py metrics` lists valid targets; sameness is a default guardrail).
5. Add one dated line to docs/NEXT.md (docs/CLIPS.md for clips work).
6. Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>, then `git pull --rebase` and push. The
   workflows push often, so retry the pull and push if the push is rejected. Never break the next scheduled run.
7. Check board shape with `python pipeline/validate.py boards/queue/<file>`. To make a new board, copy one from
   boards/done.
