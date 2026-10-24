# The writer's models and the upload ceiling (built 21 October 2026)

Charlie's decisions, 20 October (22:40 to 22:45 UK):
- He has Claude Max. Claude may write Shorts only after the free Gemini models AND other companies' free models are used up.
- Use as many companies' models as possible and test them on real Shorts: the data decides which model writes more.
- The ceiling is YouTube's upload limit: as many Shorts (tests) a day as it allows.
- Keep his Claude usage low: GitHub does the work and a Claude session is only needed for changes.

## 1. One door, a chain of models (pipeline/factpack.py)
factpack.gemini(prompt, schema=None, timeout, temperature, lite, prefer=None) -> (json, model) is still the one door
every caller uses. The order, each model skipped for the rest of the run once its daily limit is hit (a per-minute limit
waits), is:
1. Gemini Flash models (the configured one, then stable before preview, Lite last; lite jobs go to Lite first).
2. Gemma instruction models on the same key (the 3 biggest, e.g. gemma-3-27b-it): no JSON mode or schema, so they get
   "reply with the JSON only" and loads_loose reads the answer (fences, a <think> block, words around the JSON).
3. Keyed free providers, only when the secret exists (all OpenAI-style, chat/completions with response_format
   json_object, dropped for a model that refuses it): GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY
   (its ":free" models, biggest context first). Each provider's /models list decides what is offered; config.json
   "providers": {"groq": ["model", ...]} pins a list. Names: "groq:llama-3.3-70b-versatile" and so on.
4. The open model on the runner: pipeline/get_llama.sh (write.yml) fetches llama.cpp; the model (config.json
   local_model, Qwen2.5-7B-Instruct Q4) is downloaded and llama-server started only when the chain reaches it.
   Slow on 4 CPUs (minutes a board), so it is the last free writer. Name: "local:qwen2.5-7b-instruct-q4_k_m".
5. Claude last: only with the CLAUDE_CODE_OAUTH_TOKEN secret (`claude setup-token` on his Mac). write.yml installs the
   CLI; claude_call runs `claude -p --output-format json --model sonnet --tools ""` with the prompt on stdin in an empty
   folder. Never for lite jobs (triage, fact extraction, translations) and at most claude_max_per_run calls a run
   (config.json, 12); the log line counts them ("claude calls").
GitHub Models is not in the chain: GitHub retired it on 30 July 2026 (docs.github.com/rest/models).
gemini_state() (the "gemini:" line in status/write_log.txt and status/factpack_log.txt) shows models out of quota and
why, timeouts, answers per model, which keyed providers were present, and the Claude call count.

## 2. The writers are tested on real Shorts
- Every board records its writer ("writer": provider:model; Gemini models as "gemini:name").
- analytics.py writer_scores() writes analytics/models.json (each Short against Shorts posted within 3 days, like
  looks); "writer" is in drivers.TESTED, so drivers.csv and the Recipe can show it.
- writer.choose_writer(): Thompson sampling over the writers that still have quota (a model with under 3 measured
  Shorts gets an early-try boost), never Claude; gemini() tries that one first (prefer) and falls down the chain if it
  fails. pipeline/llm_probe.py (push requests/llmprobe.txt) tries models one by one on a real pack without queueing.

## 3. The most Shorts YouTube allows
config.json: daily_limit 40, slots_per_day 40, slot_every_minutes 24 (07:30 to 23:06 UK), runs
{"evening": 10, "morning": 18, "afternoon": 12}; the afternoon run makes up to 30 when the morning fell short.
quota.py keeps uploads inside the API allowance (40 x 100 units + extras under 10,000); render.yml runs 6 at a time.

## 4. Weak Shorts: remake, don't delete
Deleting gives no upload back and loses the slow search views that make most of our views, so weak Shorts stay up (the
title swap already runs). The morning run writes one "remake" a day: the weakest Short under half of typical after
48 hours (analytics/shorts.csv) whose subject is still in the day's fact packs gets a new Short with a different angle,
hook and title ("remakes": the old id on the board).

## 5. Checks
tests/ run offline with stubbed HTTP (test_model_chain.py covers Gemma, the providers, waits, prefer, Claude's cap and
lite rule, the writer's choice, writer scores and the remake pick). A real run: push requests/write.txt with "dry 2"
and read status/write_log.txt.

## What the real runs showed (20 October, 22:20 to 22:40 UTC)
- write.yml "dry 2" (status/write_log.txt): 3 boards (2 plus a reserve), each tagged with its writer
  (gemini:gemini-flash-latest, gemini:gemini-3.5-flash-lite); llama.cpp fetched in a second ("local": true), no keyed
  providers, 0 Claude calls. 5 Flash models were already out of their 20 a day; the Lite models carried the run.
- llmprobe.yml (status/llm_probe/): gemma-4-31b-it wrote a clean board in 192 s; gemini-3.5-flash-lite in 2 s; the open
  model (Qwen2.5-7B Q4 on the 4-CPU runner) in 456 s (prompt 14 tokens/s, answer 5 tokens/s) but short (44 words), so
  it only ever writes as the last free resort and its boards go through the usual fixing round.

## 21 October: every Short a test, more of what works, the ceiling learns
Charlie (23:00 UK): make the money back; every Short a data test; more of the same when a Short performs; try every
multi-part form and top 10s from the trending data; only free keys; Pexels issues no new keys; any legitimate source.
- Series: the "series" test now has three arms (single, two parts, three parts) and applies to news too, on any pack
  with 3 facts a part or more; parts link each other in the comments (engage.series_links) whatever their number.
- Top 10s and true stories that ride the day's trending subjects: evergreen_packs() gets the top 12 trending topics
  and asks for about half its ideas on them (trend_share(): the share follows drivers.csv, source "Trend-tied" against
  "Evergreen"). Searches that already bring viewers (analytics/search_terms.csv, from YouTube Analytics' YT_SEARCH
  detail) go into the same plan, so the writer makes more of what people type.
- More of what performs: a breakout is now 2x typical with 150 views or more (config breakout_times, breakout_min_views);
  when no fresh pack covers a breakout, followup_pack() builds one from the Short's own pages (Wikipedia first). Kinds,
  categories, formats, looks, slots and writer models already weight themselves by their measured lift.
- The upload ceiling learns (quota.py, status/upload_limit.json; config upload_limit_step 6, max 72, min 10): +6 after
  each filled day with no refusal, down to what YouTube accepted when it refuses one (uploadLimitExceeded). The writer's
  runs scale with it (runs are shares of the day), slots spread over 07:30 to 23:30, publish.py uploads up to it.
- factpack_topics 30 (news supply for a bigger day). Pexels off in config (Pixabay and NASA carry the background video).
- Not done, on purpose: reuploading other creators' viral clips. YouTube's reused-content rule rejects a Partner
  Program application for exactly that, and Content ID claims or strikes follow; our own Shorts on the viral moments,
  official press and trailer files, Commons and NASA footage, his own gameplay, and (on a separate channel) an official
  clipping programme are the legitimate routes.

What every Short tests (recorded on the board and scored in analytics/drivers.csv, models.json, looks.json, slots.json):
writer model; kind (news, breaking, follow-up, remake, evergreen question, top list, true story, fiction); topic source
(Google Trends, YouTube, Wikipedia, Apple Music, Football, Launches, Trend-tied, Evergreen, Follow-up, Requests);
category and format mix; hook type and length; ending (loop, question, follow line); title wording (search phrase or
curiosity); first frame (cover or photo); angle research shown or hidden; series (1, 2 or 3 parts); look (captions,
voice, camera energy, colour grade, opening); music mood; posting slot; the alternative title swap after 24 hours;
the channel's comment question and replies.

## 21 October, 00:20 to 01:00 UK: posting round the clock, the clips channel
- Slots cover all 24 hours from slot_first (a third of viewers are American, a fifth Asian); a posting day runs 07:30
  to 07:30, so a run after midnight still fills the night ("afternoon 8" pushed to requests/write.txt wrote 6 for the
  night of 20 October: a follow-up from a breakout's own pages, written by Groq, and five evergreen Shorts).
- A request line may name the run: "afternoon 8", "evening 10", "morning 18" (WRITE_RUN).
- validate.check no longer crashes on a board with no beats (a Groq board did; the writer now asks again).
- No gameplay uploads from Charlie (fiction Shorts use stock video of game-like motion).
- Quickplay Clips (@QuickplayClips-x9b) exists: docs/CLIPS.md has the plan and his steps; the social workflow can sign
  it in (channel "clips"); the YouTube sign-in link is now always in status/youtube_connect*.json. Waiting on: the
  channel's sign-in, the campaigns he joins (clips/campaigns.json), TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET.

## Still open
- Charlie's optional secrets: GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY, CLAUDE_CODE_OAUTH_TOKEN
  (https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new).
- CLAUDE.md is the old guide for Claude writing runs; replace it with a short current one once Charlie says yes.

## 21 October, 19:00 to 21:00 UK: the stop rule, the Monday report
- Charlie: "posts with little to no views after a week should not be posted about again as clearly that strategy
  doesn't work". drivers.py: a dead floor (a fifth of the typical week-old Short's views, at least 20, once 5 Shorts are
  a week old); a choice with 3 or more week-old Shorts under it, on 2 days, gets verdict "stop": the writer leaves that
  category, format, hook style, kind or test arm out for good (boosts STOP, arms(), share() 0, the recipe's "Never again"
  line), and a dead Short is never followed up or remade (weak() skips drivers.dead()).
- Charlie: a weekly analytics update of what changed, what is measured, and whether the optimisation works as more is
  posted. pipeline/weekly_report.py and report.yml (Monday 08:27 UTC, or a push of requests/report.txt): the week in
  numbers against the week before (Shorts, views gained from hourly.csv, median views a day after posting, subscribers,
  YPP pace), Shorts that followed the data's rulings against the rest, every ruling that moved, what was built (the
  dated headings here and in CLIPS.md), what was stopped, what is measured, the clips channel's money. analytics/weekly.md
  and a GitHub issue labelled "weekly" (the GitHub app on his phone).
- His concern that the testing shows no improvement yet: the first rulings only landed on 21 October (5 Shorts per
  choice and 2 days of views needed), median views per Short rose from about 100 (16 to 18 October) to about 200 (19 to
  20 October), and the last 24 hours brought 5,974 views against 14,497 all time. The report makes this visible weekly.
- Charlie: full portrait visuals with the text over the picture, clear of its main feature. render3.py face_focus()
  (OpenCV, now in requirements.txt): a picture's window follows the largest face (fx, fy) when the board gives no focus,
  for full-screen pictures and cards alike; when the person sits low in a full-screen picture and the beat has no
  graphic, that shot's captions move to the top band (template3.html, capTop). The clips channel got the same rule in
  its "full" layout. Untested on a real render until the next write run; the change is guarded (no face, no change).

## 22 October, 00:30 to 01:30 UK: relatable, and a minute or two long
- Charlie: content must be relatable ("the Tetris one is so niche"), to reach more people's algorithm. RULES: the Short
  is for the millions who know the subject from their own life, told through what it means for the viewer; no business
  history, licensing, corporate timelines or fan lore; a niche subject gets an ordinary person's angle or {"skip":
  "niche"}; every board records "appeal" ("everyone" or "fans"), now a feature in drivers.csv and shorts.csv so the data
  shows what mass appeal is worth. The evergreen planner asks for ideas most people know (appeal 4 or 5 only). The hook
  may not open "Discover", "Learn", "Here's how", "Today we", "Let's look" (validate.py errors, the model fixes it).
- Charlie: test shorter and longer Shorts, a minute and two minutes, the long ones packed with more to keep viewers
  watching. Length arms "about 60 s" (150 to 180 words, 10 to 14 beats, the wildest fact last) and "about 2 min" (280 to
  340 words, 18 to 26 beats, a twist every 10 seconds, a running count, a reason to stay said out loud); only on packs
  with 9 or 16 facts (LONG_NEEDS), never padding. validate.py reads the arm from the board's test; a board that comes
  back at a normal length is kept as written. drivers.py bands: "45 to 89 s" and "90 s or more".
- First full run with the new rules (22 October, 08:48 UTC): 7 of 18 written; "appeal": "everyone" on the Gemini
  boards, the length guard downgrading thin packs, no empty boards. The evergreen top lists all failed on "only 2 or 3
  checked facts": Wikipedia list articles keep their rankings in tables and page_text dropped tables. factpack.page_text
  now keeps tables for Wikipedia pages (rows read as "| 1 | Minecraft | 300 million |"), which also feeds the long arms.
- The afternoon run (13:39 UTC) still dropped every top list ("only 1 or 2 checked facts") with trafilatura's tables
  on, so factpack.wiki_tables now parses a Wikipedia page's first data tables itself into lines like "1 | Minecraft |
  300,000,000 | Multi-platform" after the prose, and the fact checker is told to quote a whole line; verify() matches it.
- Charlie: full portrait footage on the main channel too, no dead space. render3.py: picture cards over the background
  video are off (CARDS only with config.json render.picture_cards true); every picture and video fills the 9:16 screen,
  framed on the face (face_focus), captions moving off a person who sits low; the background video now plays only
  behind graphic beats. First real render: the 18:23 UTC evening run.
- A board was lost (QD-124, 15:33 UTC): the write job's push failed five times with "CONFLICT (file location):
  boards/queue/QD-124.json added ... inside a directory that was renamed in HEAD": the render job had emptied
  boards/queue meanwhile, which git's rebase read as a folder rename. Every workflow's save step now sets
  merge.directoryRenames false (reproduced and confirmed in a scratch repo). Any write run finishing while the queue
  emptied would have lost its boards the same way, part of the shortfall.

## Writer quality upgrade (Charlie, 23 October): build next
The writer model is now the limiting factor. The 23 October morning run: Gemini 3.5 Flash-Lite answered 32 calls and
3.6 Flash 7; the stronger Gemini models hit 20 a day or timed out (flash-latest, 3.8 and 3.7 twice each); Groq and
OpenRouter keys are set, but Groq wrote nothing, because keyed providers are only tried after every Gemini and Gemma model.
1. Order the writing step (writer.write_one and its fix rounds) by writing quality, not provider: the strongest free
   models first (Groq's largest instruction models and OpenRouter's best ":free" models from each /models endpoint; big
   general chat models such as Kimi K2, GPT-OSS 120B, Llama 4 Maverick, DeepSeek or Qwen3 235B before small or vision
   ones), then Gemini Flash (writing calls get 240 seconds), then Gemma. Gemini Lite and the local model write only when
   everything else failed. Lite jobs keep their order. Seed the writer test's Thompson choice from this order.
2. Claude, capped, as editor and test arm (only with the CLAUDE_CODE_OAUTH_TOKEN secret, already allowlisted): after a
   free model's board passes every check, one short claude_call (the board plus a short brief, not the whole RULES prompt)
   rewrites only meta.title, meta.alt_title, meta.comment, beat 0 and the last beat, keeping every fact, the word counts
   and no dashes; validate and fact-check again, keep the original if anything fails; board["editor"] = "claude".
   Claude also writes 1 board in 4 in full as a test arm. Caps in config.json: claude_edits_per_day 24,
   claude_writes_per_day 8, counted per UK day in status/claude_usage.json, shown in the "gemini:" log line.
3. Score writer and editor combinations in analytics/models.json and on the hub; when Claude-edited or Claude-written
   Shorts don't earn more views, their share falls back by itself.
4. Stubbed tests, every test run, then a real "dry 2" run; read status/write_log.txt.
- Built 23 October (portal request): factpack.writing_order() and gemini(writing=True) put a Short's script and its fix
  rounds in quality order (quality(): Kimi K2, GPT-OSS 120B, Maverick, DeepSeek, Qwen3 235B, Mistral Large first; 70B
  models next; vision, coder and small models last), then Gemini Flash (240 s), Gemma, weaker keyed models, and Lite, the
  runner's model and Claude only when all else failed; providers list their best writers, not the first few. The
  writer's Thompson choice is seeded from that order (never Lite, local or Claude). writer.claude_edit(): Claude rewrites
  title, alt_title, comment, first and last lines of a passing free-model board; numbers kept, length within 2 words, no
  dashes, validated and fact-checked again, else the original stays; board "editor": "claude". claude_arm(): Claude
  writes 1 board in 4. Caps config.json claude_edits_per_day 24 and claude_writes_per_day 8 in status/claude_usage.json
  (UK day), shown in the "gemini:" log line. analytics/models.json adds "editors" and "combos"; both Claude shares fall
  back by views (claude_shares) after 5 measured Shorts. Hub: Editor column and a "Writers and editors" table.
  tests/test_writer_quality.py.
- 23 October, first real run (13:32 UTC): Groq GPT-OSS 120B wrote 2 boards, OpenRouter Nemotron Ultra 1, but Groq was then benched for the run on one "prompt too large" (its free tier caps tokens a minute); now an oversized prompt skips only that call, and the model is passed over after 4. No Claude edits or arm boards: the CLAUDE_CODE_OAUTH_TOKEN secret is empty on the runner (allowlisted, never set); Charlie adds it. Most empty places were packs with too few facts, not the writer.
- 23 October: Claude use on the hub (Charlie: worried about his allowance). factpack.claude_call counts every call in status/claude_usage.json (UK day: calls, edits, writes, the last result, 14 days of history; claude_note, claude_usage); the Overview tab shows today against the caps, the last call (worked or failed and why) and the last 7 days. Only write.yml holds the token, so that file sees every call. The token was first pasted cut short ("Invalid auth token" at 17:04 UTC); Charlie re-set it.
- 23 October, evening run (19:07 UTC): the Claude token works (4 calls, last "ok"); Claude wrote 1 board, but it was a part of a 3-part series dropped when part 3 came back "niche". The editor answered both times but every edit was thrown away: its brief missed the title emoji rule and one first line ran 3 words long. The brief now gives the emoji rule and each line's word count, and a line that misses keeps the writer's version while the rest of the edit still counts.
- 23 October night (Charlie: "make it extremely robust"): fact yield. factpack.verify() now matches a misquoted sentence to the page's own words (near(): 85% of its words and every number, within twice its length) instead of dropping it; facts_from() asks the strongest free writers (writing order, never Claude) for a second opinion when Lite leaves fewer than 4 facts (or the kind's minimum for evergreen packs) and checks both answers together; the prompts spell out the JSON shape for non-Gemini models; build() triages twice the topics and skips ones a recent Short covered (6 of 11 evening packs were wasted that way); writer.unwiki() drops "according to Wikipedia" from narration instead of failing the board, and pack_text marks Wikipedia as a reference never to cite. tests/test_fact_yield.py.
- 23 October night (Charlie: time and geography targeting, e.g. music when the Americans watch). The 40 slots a day fill every half hour, so the hour itself barely varied. analytics.slot_scores adds "bands" to slots.json: each category's Shorts by UK quarter of the day (00-06 is the American evening), views against typical. plan.slot_picker moves a board to the first free slot in its category's best quarter when that is at least 15% better (shrunk towards the quarter's overall score, 12 measured Shorts needed), within 18 hours (6 for news); 1 board in 5 keeps the first slot so every hour stays measured. First numbers: Music 3.5x in 00-12 UK against 1.2x in the afternoon; all Shorts 2.2x in 06-12 against 0.5x in 18-24. Hub: "When each kind does best" on the Daily Shorts tab. tests/test_slot_bands.py.
- 23 October night (Charlie: fewer, better; follow the data). quota.target(): 15 Shorts a day (config shorts_per_day) under the learned ceiling; the writer runs, the reserve top-up and the slots (15 a day at the learned best times) follow it. config volume_test: 24 to 30 October against the 40 a day before; analytics.volume_test judges it from the channel's daily views on 1 November (kept at 90% or more of before, else back to 40), writes status/volume.json and a decisions.csv line. writer.category_shares(): each category's share of the day from drivers.csv lift squared (now Music 33%, Sport 27%, Film 24%, the rest 4% each, so they stay measured); a pack over its share waits for spare places; the evergreen planner gets the same shares. tests/test_volume.py.
- 23 October night (Charlie: are unclear Shorts lost?). They were: 4 boards (QD-056, 076, 086, 126) failed "unclear narration" after two voices and never posted. run_board now tries a third read (the house voice 15% slower), keeps the clearest, and lets one middle beat through when the speech check still heard a quarter of it (status "qa_note", not a flag: any flag holds a Short for approval in upload.py). The length check allowed 75 s, so every "about 2 min" arm would have failed: it allows 180 s for that arm.
- 23 October night (Charlie: measure and record everything; when something goes wrong, the data should say where and why). pipeline/funnel.py counts each day's stages for both lines (packs, written, rendered, failed and why, uploaded, public; clip moments, made, uploaded, refused, Instagram, submitted, views), writes status/funnel.json and a row a day to analytics/funnel.csv, and names any stage that got nothing while the one before had work. alerts.py runs it each evening and opens "⚠️ A pipeline stage is stuck" (it flags the clips today); the evening check now measures against the chosen 15, not the ceiling. Hub: "Pipeline today" on the Overview.
- 23 October night: "Held at 3 s" over 100% (26 of 28 measured Shorts, up to 319%) is real, not a bug: YouTube's audienceWatchRatio counts replays and loops, so it is views of that moment per view. The hub says so.
- 23 October night (Charlie: run for months with little from him, adapt to rule and law changes). pipeline/policy_watch.py (policy.yml, daily 07:41 UTC) reads the YouTube blog, Creator Insider and news searches (Shorts policy, Partner Programme, reused content, AI disclosure, Reels reach, Ofcom Online Safety Act, ASA influencer rules, clipping campaign rules); a free model sorts items into act, watch or ignore; act and watch go to docs/POLICY.md, act opens an issue labelled policy. News text never reaches a prompt that writes or posts. alerts.py also checks every job ran successfully inside its expected hours (STALE_HOURS) and opens an issue when one silently stops (the clips social step never ran for days); clips, policy and audit failures now raise alerts too.
- 23 October night: the first watch run read months of back news and opened 23 issues; they are consolidated in #27 (Partner Programme thresholds double from 1 February 2027: 20 million Shorts views in 90 days or 8,000 watch hours; reach cut for barely changed reposts; AI labels). The watch now reads news from the last 14 days and opens one issue per run.
- 23 October night: Claude caps lowered for Charlie's allowance (the 19:07 Mac run failed on his usage limit): 12 edits and 4 boards a day, 6 calls a run. analytics summary "ypp.from_2027" (20 million Shorts views in 90 days, or 8,000 long-form watch hours in 365 days, measured from YouTube Analytics creatorContentType VIDEO_ON_DEMAND) shown under the hub meters; the weekly job is watched for silent stops. Hub tab "Export for Claude": one click builds a single Markdown file (about 190 KB) of every number, test, decision, log and note to drag into a Claude chat. docs/WEEKLY_REVIEW.md: the weekly Claude review prompt for Charlie to create as a scheduled task (Claude was not permitted to create it).
- 23 October night (Charlie: why no live feedback from GitHub?): the hub Overview now shows "Live: GitHub jobs right now", each job's latest run from GitHub's public API (running, worked or failed, when, what started it), refreshed with the page.
- 23 October night: the 20:39 analytics run failed: status/policy_seen.json (a JSON list) sat among the Short status files that analytics, plan, run_board and review_page read as status/*.json. Moved to status/policy/seen.json, and those readers now skip anything that is not a status object.
- 23 October night (Charlie: be proactive for GTA 6, out 19 November 2026, as well as reactive). pipeline/watch.py (trends.yml, before trends.py) measures every config.json "watchlist" item each run: Wikipedia views momentum (yesterday against the 14-day median), news articles in 24 hours, Google Trends, Wikipedia top pages and YouTube charts, YouTube suggestions; phase from the date (build-up within 45 days, launch 3 days before to 7 after) and surging (momentum 1.5, 15 articles a day, or Google Trends). trends.py adds the main term and, beyond steady, its angles as "watchlist" topics (kept by the fact packs like requests); the writer gives each item its own places a day (1, 2, 3 surging, 4 launch) outside the category shares, ranks them first, puts the item's rules in the brief (GTA 6: entertainment news only, never violence or crime, never its songs) and marks boards "watch"; the evergreen planner rides items past steady; the scout adds heat to their campaigns (0.5 build-up, 1.0 surging, 1.2 launch); one issue when an item first surges; analytics/watch.csv keeps every day; hub table "Watchlist". Chrome standing jobs: look for watchlist campaigns to join; on Mondays link the week's top 10 Shorts to the weekly long video (related video) and add its end screen. Uploads now go up under a file name made of the title (youtube.named_copy). Money shows pounds next to dollars on the hub and the clips page (frankfurter, else open.er-api.com, else status/fx.json from the evening check), and the money issue too.
- 23 October night (Charlie: get every data source we need). Where views come from: the channel split was already kept (analytics/traffic.csv: 77% Shorts feed, 22% search); now each Short also gets yt_feed_pct and yt_search_pct in shorts.csv (YouTube Analytics insightTrafficSourceType per video, full runs), shown as "From the feed" on the hub with a "Where the views come from" table. Clips: stats.csv gets ig_views, ig_reach, ig_watch_s from analytics/cache/instagram.json (the clips post on the main Instagram, whose insights analytics already reads). Competitors: pipeline/competitors.py (trends.yml after analytics, once a UK day, about 800 units behind quota.allow) keeps the most-viewed English Shorts of the last 2 days per category and watchlist item in analytics/competitors.csv (60 days) with title features, and analytics/competitors.md compares winners' titles with ours; the writer shows each board its category's top 4 titles of the week as angles to beat, never copy; hub "What wins for everyone else". No new keys or accounts were needed.
- 23 October night (Charlie: mass scrutiny, missing markets). Four new market categories on test: Animals, Food, Cars, History (writer, validate, analytics, triage and the planners; YouTube categories 15, 26, 2, 27; background fallbacks). A category with no measured Shorts explores at 8% of the day (writer.EXPLORE) instead of without limit, then follows the data like the rest.
- 23 October night: subscribers are the Partner Programme blocker (9 from 19,500 views; a mixed-topic channel gives viewers no reason to follow), so a new test "franchise": "named" Shorts open their title with a recurring series per category and its number ("Song Secrets #12: ...", writer.FRANCHISE, numbered across every board folder), "plain" ones do not. Recorded on boards and in shorts.csv; drivers.py scores it ("Named series") with subscribers per 1,000 views alongside views.
- 24 October, overnight: a YouTube sign-in that Google reports as expired or revoked (invalid_grant) no longer counts as "a sign-in outside the studio account": the identity audit marks it "expired sign-in", posting elsewhere continues, and a separate issue "🔑 A sign-in has expired: reconnect it" names it. Before, one expired token would have stopped every posting workflow. (The four sign-ins carry no expiry date, so the Google app is not in Testing.)
- 24 October, overnight, from the first real run of tonight's research: competitors.py searched "gaming" and "movie" and got Spanish, Hindi and Indonesian film recaps; now it searches Shorts like ours ("music facts", "football facts" and one per category, US region, 25 results), keeps English titles only (Latin script and two common English words), and a day the YouTube allowance cut short is finished by the next run instead of counting as done. The junk rows were cleared. Triage and trends.py now skip practical searches with no story ("movie times", showtimes, near me, login, weather): the 23:12 run built a pack for "movie times".
- 24 October, overnight: the watchlist grows from GTA 6 to the next big dated events, so the channel is ready before each one peaks: Avengers: Doomsday and Dune: Part Three (both out 18 December, build-up from 30 days before), The Game Awards (10 December, Los Angeles, build-up from 21 days before). Each item can set its own lead time (lead_days). A steady item (far off and quiet) is now only measured: no topics and no places until it builds up or surges (before, every item took a place a day, so four items would have taken four forced Shorts a day); a trailer or big news turns it surging that run (15 articles a day, Wikipedia interest 1.5 times usual, or Google Trends). Terms kept specific (no bare "Doomsday" or "Game of the Year", which match unrelated trends), and the scout's watchlist match ignores names under 4 letters.
- 24 October, overnight: an empty model reply is no longer read as an answer. loads_loose turned an empty reply into {}, so a model that sent nothing (blocked, or its thinking used every token) "answered" and the chain stopped there: last night's clip planner took "no moments" from two OpenRouter models three times over (22 minutes, two campaigns with no clips). Now an empty reply moves straight to the next model, is counted ("empty answers" in the run's model log), and a model empty twice in a run is passed over like one that timed out twice. Applies to fact packs, the writer and the clip planner alike.
- 24 October, overnight: the YouTube allowance guard was blind to the main channel's uploads. They happen in render.yml's upload job, which wrote status/quota/render.json and then threw its workspace away (only the record job commits), so the guard counted clips (5,300 units on 23 October: 53 clips), engagement (1,960) and searches (406) but none of the ~15 Shorts (~1,500): the real day was about 9,200 of 10,000. Now the upload job passes its record to the record job, which commits it. uploads_left() now keeps room for the planned Shorts still to come (quota.target(), 15 in the test) instead of the ceiling (40), which held back 2,500 units every day. And clip uploads now ask the guard first: when the rest of the day's allowance is needed for the Shorts, a made clip waits for the next run (or the reset at 08:00 UK) instead of risking a Short that cannot upload. The Shorts come first; clips use everything else.
- 24 October, overnight: dry-run boards (tests that never go out) no longer count as covering a topic, following up a breakout or remaking a weak Short. The dry test's follow-up of QD-135 (Tate McRae, 31.5 times the usual views) sat in boards/ready and stopped the real follow-up of the channel's second-best Short; the next write run can now make it (breakouts qualify for 72 hours).
- 24 October, overnight: the day's target on the posts-by-day page and in the evening alert is now the chosen number (quota.target(): 15 in the fewer-better test, one fewer on Sundays) instead of the ceiling (40). The alert "Fewer Shorts went out than planned" had been comparing 19 against 40 every evening; today's stored target corrected to 15.
- 24 October, overnight: a watchlist news surge is now relative. A big film is written about 20 times a day every day, so "15 articles in 24 hours" would have kept Avengers: Doomsday and Dune: Part Three surging (3 forced Shorts a day each) on ordinary coverage. Now news counts as a surge at twice the item's usual articles a day (the median of its last 7 days in analytics/watch.csv) and at least 15, or 40 or more while it has under 3 days of history. Wikipedia momentum (1.5 times usual) and Google Trends still count as before.
- 24 October, overnight: a Short is no longer lost to one unclear beat. Every board the pipeline has ever lost but one went the same way: Chatterbox garbles a single long sentence, all three reads (the look's voice, George, George 15% slower) fail the ear check on that beat, and the board goes to boards/failed (QD-056, QD-076, QD-086, QD-126, and QD-147 tonight). A stubborn beat is now read again as two short sentences, cut at a comma or before a joining word and joined with a short pause (run_board.halves and split_read); the better read replaces it in the manifest and the Short goes out, with status "voice_note" saying which beats were split. Shorts lost this way were about 8% of the day's output.
- 24 October, overnight: a slow Ubuntu mirror no longer eats a job's time. It stalled the clips job 37 minutes and a render job over 20 tonight. Every workflow that installs system packages now checks first (dpkg -s) and installs only what the runner is missing, which is usually nothing: the GitHub image already carries ffmpeg and the DejaVu fonts, so the step is a second instead of minutes. When something really is missing, apt retries 3 times with 30 second connect timeouts, update is capped at 10 minutes (and skipped on failure, using the runner's own lists) and install at 15. render, clips, social, music, voices, voicebank and weekly.
- 24 October, 02:20 UK, from the first live try (run 40045396682): the two-sentence re-read of QD-147's stubborn beat worked exactly as meant, both halves at 100% of words heard against 33% for the whole sentence, but the Short still failed. The check was measuring the joined audio a second time instead of trusting the two halves' own checks, and it replaced the beat's audio before deciding. Now the halves' own scores decide (the worse half must beat the read we have and reach 50%), the numbers are printed either way, and the audio is only replaced once the split is accepted.
- 24 October, 02:50 UK: confirmed live. QD-147 ("Jorja Smith sings at the Amy Winehouse tribute"), lost twice to its first sentence, rendered and went on the schedule: "beat 0 read as two sentences", no weak beats. The first Short saved by the fix.
- 24 October, 03:35 UK: of the five Shorts ever lost to one unclear sentence, three are now on the schedule. QD-147 and QD-056 were saved by the two-sentence re-read ("beat 0", "beat 3"), QD-076 by the three reads alone (a different voice heard it this time). QD-086 (two stubborn beats) and QD-126 are still refused and stay in boards/failed, which is the safe answer: a Short nobody can hear should not go out.
