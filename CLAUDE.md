# Quickplay Daily: how it runs (21 October 2026)

GitHub does everything; a Claude session is only for changes Charlie asks for. Nothing waits for a person (approval
"none" in config.json).

## The line
- trends.yml (08:10, 12:47, 18:23 UTC, breaking checks 06:47, 10:47, 15:47): pipeline/trends.py finds what people are
  searching for (free sources), pipeline/factpack.py builds checked fact packs (trends/facts.json), pipeline/analytics.py
  refreshes analytics/ (what works, by every choice a Short makes).
- write.yml (after every trends run, or a push of requests/write.txt such as "afternoon 8" or "dry 2"): pipeline/writer.py
  writes JSON boards into boards/queue from the packs. Models, one door (factpack.gemini): Gemini Flash, Gemma, Groq,
  Mistral, SambaNova, Cloudflare, OpenRouter free models (only with secrets), llama.cpp on the runner, Claude last
  (CLAUDE_CODE_OAUTH_TOKEN is Charlie's allowance: 4 edits a day, no test boards, at most 3 calls a run; config claude_*).
  Every board records its writer and its tests.
- render.yml renders and checks each board; publish.yml (hourly) uploads to YouTube in slots that cover all 24 hours,
  up to the learned ceiling (quota.py, status/upload_limit.json: 40 a day, rising while YouTube accepts everything);
  social.yml posts to Instagram and Facebook; engage.yml comments and replies; alerts.yml, weekly.yml, voices.yml.
- Every Short is a test (kind, source, format, hook, length, ending, title, first frame, series, look, slot, writer
  model); analytics/drivers.csv, models.json, looks.json and slots.json score them and the next choices follow the data.
  A choice whose Shorts have little to no views a week on is stopped for good (verdict "stop"); a dead Short is never
  followed up or remade.
- Freshness gate (Charlie, 24 October): a time-sensitive Short goes out after its day only with evidence its story is
  alive (pipeline/freshness.py: trends, a Wikipedia surge, news), else boards/expired; a clip, test clip or submission over
  30 hours late needs heat or views. Every decision: analytics/late_uploads.csv.

## Where to look
- The hub, everything on one page for Charlie: https://quickplay-studio.github.io/quickplay-autopilot/hub.html (docs/hub.html;
  it reads the live repository files in the browser, so it needs no rebuild; add a tab there when something new is worth watching).
  Its Overview opens with "Your actions this week": status/actions.json (Charlie's to-dos with steps and links; a session adds an
  item when only he can do something and sets done true once it is done) plus open issues labelled needs-charlie
  (alerts.raise_issue(..., labels=["needs-charlie"])).
- status/write_log.txt and status/factpack_log.txt: the last writer and fact pack runs (models, quota, what was written).
- `python pipeline/digest.py` and `python pipeline/health.py`: one-screen state. status/<id>.json: one Short's life.
- docs/NEXT.md: what was built and why, newest at the bottom; docs/CLIPS.md: the clips channel plan.
- analytics/insights.md: the Recipe from the data; analytics/decisions.csv: every change made from it; analytics/weekly.md:
  the Monday report (report.yml, a GitHub issue labelled weekly). Clips: docs/clips.html (money and views per campaign),
  clips/submit.csv (GitHub submits the links itself, submit.py), docs/CLIPS.md.
- docs/CHROME_JOBS.md: the jobs the Mac task does in Charlie's Chrome (cookies, joins, account keys); a cloud session
  adds a job there (or fires the task with the job text) instead of trying to use a browser itself.
- tests/: offline tests with stubbed HTTP. Run them all before every push.
- The identity guard (Charlie, 22 October): pipeline/identity.py and audit.yml (every 6 hours) resolve every sign-in the
  automation holds and check it is the studio Google account's own Quickplay channel, page or profile (config.json
  "accounts": ids, the Quickplay name rule, the secrets allowlist, own-site cookies only in tokens/login_*.enc). A mismatch
  opens the issue "🔒 Security: a sign-in outside the studio account" and every posting workflow stops at its first step
  (identity.py gate) until the next clean audit. A new secret is added to the allowlist by hand, on purpose. The Mac
  Chrome run checks the profile's Google account first (docs/CHROME_JOBS.md).

## Channel rules (non-negotiable)
Anonymous, family-friendly, UK English ("Tuesday 20 October", colour, favourite). Never politics, crime, health claims,
money or investing advice, adult content or gambling. Never other creators' footage without their permission (the
clips channel uses only campaign-permitted footage). No em or en dashes anywhere. Nothing invented: every claim cites
its source. Weak Shorts stay up (a remake, never a delete). Free keys only; no paid tools until the channel earns.

## Working rules (Charlie)
- Terse, conclusion-first replies; step-by-step lists with every link; no recap messages. Keep his Claude usage low:
  read only what a change needs, never whole data files.
- Touch only the studio account and this repo. Never type passwords or create accounts; keys only in GitHub secrets.
  Ask before anything new that is public, any download to his computer or any purchase.
- Never break the next scheduled run: run tests/, commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>,
  `git pull --rebase` before each push. Test a writer change for real with "dry 2" in requests/write.txt and read
  status/write_log.txt.
- Every change pushed gets a ledger row: `python pipeline/changes.py add --area .. --change .. --hypothesis .. --target ..
  --guardrails ..` (analytics/changes.csv; `metrics` lists targets; verdicts and the trade-off issue come by themselves).
- Board shape: copy any board in boards/done; validate with `python pipeline/validate.py boards/queue/<file>`.
- Supply chain (Black October, 22 October 2026: poisoned LiteLLM and OVHcloud releases stole keys): every workflow installs
  packages with pip 26.2.1 and `--uploaded-prior-to P7D`, so nothing published in the last 7 days reaches a runner that
  holds the keys; npm's global installs use `--before` 7 days ago. Keep both on any new install line; pin exact versions
  where a package matters. No PHP anywhere in this project (PHP2Shell does not apply).
