# Quickplay Daily: how it runs (24 October 2026)

GitHub does everything; a Claude session is only for changes Charlie asks for. Nothing waits for a person (approval
"none" in config.json).

## The goal (Charlie, 26 October: every change serves it)
Reach the YouTube Partner Programme, or find a clipping strategy that makes real views and money. YPP counts engaged
views (viewers who stay past the opening): the expanded tier is 500 subscribers and 3M Shorts views in 90 days; from
1 February 2027 full YPP needs 1,000 subscribers and 20M (the Shorts pool 10M). Say in each change which of the two it
helps and which number it should move; the ledger target (changes.py) is that number.

## Token budget (Charlie, 24 October: his allowance is shared with other projects)
Read this file, then `python pipeline/digest.py` (one screen); `tail -n 40 docs/NEXT.md` only when history matters. Never
open a data file whole (analytics/*.csv, clips/*.csv, status/*.json, boards/): `head -1`, `tail`, `grep` or a one-line
aggregate. Hand log reading, number questions, test runs and dated doc lines to the Haiku agents in .claude/agents/
(quickplay-logs, quickplay-data, quickplay-tests, quickplay-docs) so only their short answers reach the main context.
Compact instructions: when the context is compacted, keep the task, the files touched, the test result and what Charlie asked;
drop tool output. Delegated work runs on Sonnet (or Haiku) in a worktree with a tight brief; a fork (the main model with the whole context) only
when the context itself is the brief. The scheduled tasks (Mac Chrome jobs every 2 hours, the weekly review, the portal) run on Sonnet.

## The line
- trends.yml (08:10, 12:47, 18:23 UTC; breaking checks 06:47, 10:47, 15:47): pipeline/trends.py finds what people search
  for (free sources), factpack.py builds checked fact packs (trends/facts.json), analytics.py refreshes analytics/.
- write.yml (after each trends run, or requests/write.txt such as "afternoon 8" or "dry 2"): writer.py writes boards into
  boards/queue. Models, one door (factpack.gemini): the strongest keyed free models, Gemini Flash, Gemma, the rest
  (Groq, Mistral, SambaNova, Cloudflare, OpenRouter, only with secrets), llama.cpp, Claude last (CLAUDE_CODE_OAUTH_TOKEN is
  Charlie's allowance: 4 edits a day, no test boards, at most 3 calls a run; config claude_*).
- render.yml renders, checks and uploads each board (its upload job) in slots round the clock: the day's number is
  quota.target() (status/volume.json, 15 in the volume test), the ceiling is learned (status/upload_limit.json). quota.py
  guards the YouTube allowance: 10,000 units, plus 100 uploads and 100 searches a day in their own buckets, shared by the
  four channels. publish.yml (hourly): approvals and the reserve. social.yml: Instagram, Facebook (a 1-a-day probe),
  TikTok off (docs/TIKTOK.md). engage.yml: comments. clips.yml: paused since 26 October (config.json clips_paused; the
  three clip channels post original Shorts through shorts_channels instead, one learning model for all four; set it to ""
  to clip again): clips made at 12:00 UTC, public at 19:00 UK; Vyro is submitted by the Mac (docs/CHROME_JOBS.md).
  alerts.yml, audit.yml, weekly.yml, report.yml.
- Every Short is a test (kind, source, format, hook, length, ending, title, emoji, first frame, series, look, slot, writer).
  analytics/drivers.csv gives a verdict only with proof (5 Shorts over 2 UK days, a 90% interval clear of typical, both
  halves agreeing); a choice with little to no views a week on is paused 14 days, then retested. 1 Short in 5 explores,
  every category keeps a floor, no writer model passes 35% before 10 measured Shorts. A dead Short is never remade.
  One pooled, channel-aware model (26 October): every channel's Shorts feed the one test round (config.json test_round,
  11 factors, "lab" = the newest lab look); analytics/round.csv gives verdicts adjusted for channel and the other arms,
  a settled factor (even or no clear difference) leaves the round, and analytics/channel_drivers.csv lets a channel
  differ only with 10+ of its own Shorts proving it.
  trend.py (26 October) watches the absolute numbers week on week and how many Shorts followed the rulings (insights.md "Is
  the channel getting better"); alerts.py opens an issue when retention falls or the recipe stops refreshing.
- evolve.yml (07:23 UTC, 26 October): pipeline/evolve.py keeps the test round full by itself. It retires settled contests (a
  winner becomes a champion, analytics/evolve.json), opens new ones by Thompson sampling on each source's record (an untried
  arm, a retest, a "gene": a writing instruction, or a refinement of an adopted one) and adopts a winning gene into the recipe.
  The proposals are its one complex step: one Claude call a run (opus), free models only if it returns nothing. config.json
  "evolve" holds the limits ("on": false restores the fixed test_round); analytics/evolve.md is the summary.
  Opening first (26 October, hooks): hook_type, first_frame, fx_opening and "opening" genes are judged on the engaged
  share (drivers.OPENING, round.csv metric "engaged", a win needs 10% and the views guard withholds one whose clear views loss cancels the gain or reaches 15%;
  engaged views lag about 3 days); evolve.focus_first reopens an absent opening factor before anything else, every
  opening_gene_every-th new gene is an opening gene (one live at a time), and their ledger target is engaged_share.
- Freshness gate (pipeline/freshness.py): a time-sensitive Short goes out after its day only with evidence its story is
  alive, else boards/expired; a clip or submission over 30 hours late needs heat or views (analytics/late_uploads.csv).
- Watchlist (config.json "watchlist", watch.py): dated events get places in their build-up and launch week, at most
  watch_share_max (a third) of the day together.

## Where to look
- Claude Code on the Mac (25 October): docs/CLAUDE_CODE.md (setup, the three routine prompts, Sonnet and Haiku defaults in
  .claude/settings.json). A new project starts from templates/claude-code-project/.
- The hub: https://quickplay-studio.github.io/quickplay-autopilot/hub.html (docs/hub.html reads the live files; no
  rebuild). Its Overview opens with "Your actions this week": status/actions.json plus issues labelled needs-charlie
  (alerts.raise_issue(..., labels=["needs-charlie"])). actions.py keeps that list true (below), so add an item there
  with a "check" (secret_works:NAME, pages_workflow, vyro_today, or a new one in actions.CHECKS) whenever one can prove it.
- `python pipeline/health.py`; status/write_log.txt and status/factpack_log.txt (tail only); status/<id>.json: one Short.
- docs/NEXT.md (what was built and why, newest at the bottom), docs/CLIPS.md (clips), analytics/insights.md (the
  Recipe), analytics/decisions.csv (the Recipe's changes), analytics/changes.csv (the change ledger), analytics/weekly.md.
- The Mac: docs/CHROME_JOBS.md (a 4 KB card), `python3 pipeline/mac_rows.py` (its work), docs/CHROME_LOG.md (one-off jobs,
  history). A cloud session adds a one-off job there instead of using a browser itself.
- Identity guard (22 October): identity.py and audit.yml (every 3 hours) check every sign-in is the studio Google
  account's own Quickplay channel, page or profile, and every secret is on config.json accounts.secrets (a new one is
  added by hand, on purpose). A mismatch opens "🔒 Security: a sign-in outside the studio account" and the posting
  workflows stop at their gate step until a clean audit. The audit also refreshes the IG_<CHANNEL>_TOKEN keys weekly.
- Live checks (24 October), run by audit.yml after the identity audit: keys.py writes status/keys.json (every sign-in and key:
  ok, expiring, failing or missing, its end date, the fix steps; the hub's Accounts tab) from the audit's own calls plus one
  cheap call per API key, and opens one needs-charlie issue per failing key or one ending within 14 days, closed when it works.
  actions.py runs each status/actions.json item's "check" and ticks it off or reopens it; an item with no check gets an
  issue, and closing it in the GitHub app ticks it off (the hub hides done items and lists them under Done this week).
- tests/: offline, stubbed HTTP. Run them all before every push.

## Channel rules (non-negotiable)
Anonymous, family-friendly, UK English ("Tuesday 20 October", colour, favourite). Never politics, crime, health claims,
money or investing advice, adult content or gambling. Never negative about a real person (admits, betrays, feuds, slammed,
mocked, fails: validate.NEGATIVE rejects it; negative turns only in fiction). Never other creators' footage without their permission (clips
use only campaign-permitted footage). No em or en dashes anywhere. Nothing invented: every claim cites its source. Weak
Shorts stay up (a remake, never a delete). Free keys only; no paid tools until the channel earns.

## Working rules (Charlie)
- Terse, conclusion-first replies; step-by-step lists with every link; no recap messages.
- Touch only the studio account and this repo. Never type passwords or create accounts; keys only in GitHub secrets.
  Ask before anything new that is public, any download to his computer or any purchase.
- Never break the next scheduled run: run tests/, commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>,
  `git pull --rebase` before each push. Test a writer change for real with "dry 2" in requests/write.txt.
- Every change pushed gets a ledger row: `python pipeline/changes.py add --area .. --change .. --hypothesis .. --target ..
  --guardrails ..` (`metrics` lists the targets; verdicts and the trade-off issue come by themselves).
- Board shape: copy any board in boards/done; validate with `python pipeline/validate.py boards/queue/<file>`.
- Supply chain (Black October, 22 October 2026: poisoned LiteLLM and OVHcloud releases stole keys): every install uses
  pip 26.2.1 with `--uploaded-prior-to P7D`, npm's global installs `--before` 7 days ago; keep both on any new install
  line and pin exact versions where a package matters. No PHP anywhere.
