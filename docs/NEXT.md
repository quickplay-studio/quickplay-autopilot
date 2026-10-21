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
