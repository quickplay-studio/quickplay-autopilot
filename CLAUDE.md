# Quickplay daily script run

You write Shorts as JSON "boards" and push them. GitHub renders, checks, uploads and schedules them on YouTube, then
posts them to Instagram and Facebook automatically (TikTok is off since 19 October). Three sessions a day (numbers
in config.json `runs`): 20:50 UK writes the first part of TOMORROW (its boards get `created` = tomorrow and tomorrow's
first slots, from 07:30); 06:50 writes most of the day from fresh trends; 12:50 writes the rest from what broke since.
Approval is "flagged": only flagged Shorts wait for Charlie, so the evening batch lets him clear them before bed.

## Spend as few tokens as possible
- Work in as few turns as you can: send independent tool calls together (all the day's WebFetch calls for every topic in
  one or two batches; all board Write calls in one message; validate every new board in one command).
- Never open status files one by one: `python pipeline/digest.py` prints everything you need in one go.
- Read only what you need: the Recipe and drivers at the top of analytics/insights.md, the topics you pick from
  trends/research.json.
- Fact packs first (see Facts): their facts need no fetching. Otherwise one reputable source is enough: stop fetching once
  one states it.
- Write boards as compact JSON (no indentation). Leave out what has a default.
- Wait for renders with ONE background command, `python pipeline/wait_renders.py <ids>`, never repeated polling.
- No rendering, no browsing beyond the sources you check, no recap messages.

## The goal
Monetisation as soon as possible, and YouTube comes first (Charlie, 19 October): it is the platform most likely to pay, so
every choice is made for YouTube views and subscribers; Instagram and Facebook get the same Shorts afterwards and never
shape what we make or when. The YouTube Partner Program needs 1,000 subscribers and 10 million Shorts views in
90 days, and the channel must get in before 1 February 2027 (after that, new channels need 20 million). That is roughly
110,000 views a day, so every Short has to earn its place. Choices follow the data: `analytics/insights.md` opens with
the Recipe from the data (category mix, and the formats, hooks, titles, lengths and times that beat typical, worked out
from every Short against Shorts posted around the same time) and the drivers behind it. Follow the Recipe; the reviews
(REVIEW.md) change the rules themselves, and every change and its reason is in `analytics/decisions.csv`.

## Channel rules (non-negotiable)
- Quickplay Daily: anonymous, family-friendly, UK English. Topics people are searching for now.
- Never: politics, crime, health claims, money or investing advice, adult content, gambling.
- Explore the subject itself. Never talk about views, virality or "why it went viral".
- No em dashes or en dashes anywhere (titles, narration, captions, descriptions).
- Copy formats from templates/formats.json only. Never reuse another creator's footage or script.
- UK style everywhere: "Tuesday 20 October", "20 million pounds", colour, favourite.

## What gets views
- Topics with big audiences searching right now: gaming, film and TV, music, sport, celebrities, streamers and creators, tech launches, space.
  Strongest signal first (Google Trends traffic, YouTube views per hour, Wikipedia views), weighted by what our own
  analytics say works. Early beats late: a fresh angle on today's story beats a recap. Skip niche topics and anything
  covered in the last 14 days (titles in boards/done, ready and queue).
- Hook (first beat): the most surprising true detail in 12 words or fewer, with the strongest real image on screen from
  the first frame. Never "X is back", "X has a date" or a slow intro.
- Length: 25 to 40 seconds (70 to 110 words) unless the story truly needs more. Cut background and throat-clearing.
- Ending: land the payoff, then either a line that loops naturally back into the hook or a short question viewers can
  answer in the comments. Alternate between the two.
- Title: under 50 characters, the searchable name first (person, game, film, team), then the curiosity, one emoji at
  the end. Never promise what the Short doesn't deliver.
- Variety: YouTube won't monetise templated, mass-produced content. Every Short needs its own angle and insight. Use at
  least 3 formats a day and never the same format twice in a row; vary hook styles and graphics; real images of the
  subject first.
- Neat and minimal (Charlie, 19 October): one thing on screen at a time. At most 3 graphic cards a Short (the hook, one
  figure, the payoff) with few words on each, and real images carry the rest; hold each image 2 to 3 seconds; no `tin`
  flash except one reveal; a name label only on a person's first appearance.
- Instagram and Facebook take every Short, as many a day as their gentle ramp allows (config.json). TikTok is off since
  19 October (it blocked every post as spam, and its Creator Rewards pay only for videos over a minute): leave out `tiktok`.
- Follow up breakouts: analytics/breakouts.csv (hourly) lists Shorts running at 3x or more the views recent Shorts had at
  the same age. Each run writes one follow-up for the strongest one not yet followed up (a new angle, the next chapter, or
  the answer to its top comment), title tied to the original. Views come in lopsided bursts; a follow-up rides the demand
  while it is hot.
- Evergreen search test (from Monday 19 October, checked 26 October): 2 Shorts a day answer a question people search all
  year in our categories (why, how, what, first, biggest), titled as the question people type. Reason: 63% of our views
  come from YouTube search (analytics/traffic.csv).
- Hashtags: 8 to 15, most relevant first (the first 3 show on YouTube, the first 5 go to Instagram and
  Facebook): exact names (person, title, team), then the franchise or show, the category, and 1 or 2 broad ones such as
  #Trending, #Gaming or #KPop. Never #viral, never anything unrelated. `meta.tags`: 5 to 15 phrases people would search.

## Facts: fast, honest, never made up
- Speed beats a second source (Charlie, 19 October): ride a trend while it is hot. A claim stated as fact needs one
  reputable source; for breaking news name it in the narration ("Variety says", "according to the BBC"). A fact pack's
  verified facts (two sources) need no naming. Cite the exact page, never a homepage or a search page.
- The viral claim can be the story: a rumour, a leak or what fans think, when the trend itself is the news. Say plainly
  that it is unconfirmed and who is saying it ("fans think", "a viral clip claims", "reportedly"), in the narration and on
  screen; never present it as fact, including in the title (a question title works: "Is X joining Y? 👀").
- Never invent anything, never say a source states what it doesn't, and nothing that could harm a real person's
  reputation (crime, illness, relationships, deaths), even as a rumour. These are what get channels struck, demonetised
  or sued.
- Fact packs (GitHub, about an hour before each run): `python pipeline/factpack.py show` lists the day's topics (numbers
  match trends/research.json) with how many facts are verified; `python pipeline/factpack.py show <n> <n>` prints the
  packs you pick, with real pictures of the subject found on its pages. Copy a pack's sources into `meta.sources` in the
  same order (add any you open yourself after them) and cite each fact by those numbers. Its one-source facts are fine
  to use with the source named.
- Good sources: the official source (publisher, studio, team, league, label, agency, NASA and the like) and
  established outlets (BBC, Guardian, Reuters, AP, The Verge, IGN, Eurogamer, Variety, Billboard, ESPN, Nature...).
  Cite the outlet's own site, never a site that reposts it. For a rumour, the source is whoever reports it.
- Say what is new today. If the trending item repeats older news (a date announced weeks ago), lead with what changed.
- List each claim in `meta.facts` with the numbers of the sources (from 1) that state it.
- Dates, numbers and names: copy them exactly from the sources. If sources disagree, say so or leave the claim out.

## Approval
`approval` in config.json: "all" means every Short waits for Charlie's OK; "flagged" means only flagged Shorts wait (the
rest upload straight away); "none" means nothing waits. Add `"flag": "<one line why>"` to a board when a human should
look first: a topic close to the excluded list, a person under 18 at the centre, heavy use of a brand's or someone's
footage, a claim you're less than sure about. Validator warnings and render checks (such as no real images) flag
automatically. Waiting Shorts sit in boards/ready with a private preview (draft release `preview-<id>`).
Reserve: evergreen Shorts written with `"reserve": true` render like any other but wait in boards/reserve (they never count
towards a day's capacity). GitHub uses them to fill any of the day's slots the writer runs left
empty (after 18:20, up to 3 a day). In "flagged" mode a reserve Short with nothing flagged needs no approval; a flagged
one waits for Charlie's "reserve approve all" (a line starting with "reserve" in approvals/).

## Steps
1. `git pull`. Run `python pipeline/digest.py` (health, what's made for today and tomorrow, failures, breakouts). Read
   config.json, trends/latest.json (short on purpose) and the top of analytics/insights.md (the Recipe). Fix and re-queue
   anything in boards/failed/ worth saving (move it back to boards/queue/).
2. Target day: tomorrow for the 20:50 evening run (every board it writes has `created` = tomorrow), today otherwise.
   Capacity this session = the smallest of: this run's number in config.json `runs` (evening, morning, afternoon);
   `daily_limit` minus boards with the target day's `created` date (queue, ready, done and failed, as digest.py counts).
   On Sundays take one off (the weekly long video, pipeline/weekly.py, uses one upload). If it is 0, go to step 7.
   The evening run also writes whatever today's runs missed (if a run was blocked), as long as today's slots remain.
3. Pick topics (see What gets views), starting with trends/requests.md: Charlie's own requests come first, then the
   trends; update that file in the same commit as the boards. Always write the run's full capacity: when strong trends
   run out, fill it with evergreen search Shorts (they never go stale, and most of our views come from search). The
   evening run picks what will still be fresh at breakfast: stories that broke this evening (often in the US), things happening tomorrow (a release, a match, a launch,
   an announcement), and the target day's 2 evergreen search Shorts. Fill the rest of the day to match the Recipe in
   analytics/insights.md: its category mix for about 80% of the day (the other 20% on whatever trends hardest), and lean
   towards the formats, hook styles, title styles and lengths it lists. Breaking news still beats the mix. The 12:50 run
   looks for what has broken or grown since the morning (trends and fact packs refresh about an hour before each run) and
   skips anything the morning run already covered. Start from the fact packs (see Facts): they cover the top topics'
   articles and Wikipedia pages from trends/research.json; open pages yourself only for what a pack lacks.
4. For each topic: read its fact pack (open sources only for what it lacks), choose a format, write the board, add hard
   names to `pipeline/pronounce.json`.
5. Run `python pipeline/validate.py boards/queue/<new files>` and fix every error. Warnings: fix them, or keep the
   board and add a `flag` saying why it is fine.
6. Commit all new boards in ONE commit to boards/queue/, push.
7. Lineup. Wait for GitHub to render with one background command: `python pipeline/wait_renders.py <new ids>` (it
   returns when each new board has a status, up to 50 minutes). Then send Charlie ONE message, starting with the line
   `python pipeline/health.py` prints (fix or explain anything it lists):
   - approval "all": each Short in boards/ready as `QD-0xx · title · length · look` (status `look`: captions, voice,
     energy, grade, opening) with its hook line and any flags, then
     "Reply: approve all, approve all except QD-0xx, or reject QD-0xx." Attach the preview videos:
     `python pipeline/previews.py <scratch dir>` downloads them, then send the files.
   - approval "flagged" (now): the same for flagged Shorts only, with their previews; if nothing is flagged, one line:
     how many Shorts went out and when the first and last go public.
   - If analytics/decisions.csv has lines dated since yesterday, end with one line per change (at most 3):
     "From the data: <change>, because <why>."
8. When Charlie replies, put his decision on one line in approvals/<YYYYMMDD-HHMM>.txt (for example
   "approve all except QD-034"), commit and push. GitHub uploads approved Shorts within the daily limit and drops
   rejected ones. Reply in one line.
9. Refresh the stats dashboard (see Stats dashboard). Finish with one line: how many Shorts and their titles.

## Stats dashboard
https://claude.ai/artifact/CErUUqubbPYWbVrN5XyhDy (private). GitHub refreshes analytics/ every hour (the full read three
times a day). Refresh the dashboard at the end of each run, and never `read` the dashboard or its page (large, never
needed): ArtifactData `list` collection "datasets" (for each document's version); then Artifact publish with `url` (the
dashboard), `file_path` analytics/<id>.csv and `asset: true` for shorts, daily, progress and hourly in every run, plus
drivers, decisions, geo, traffic, audience and regions in the evening run only (they change slowly); then ONE ArtifactData
`batch` of `update` writes for the files just uploaded (collection "datasets", doc_id <id>, if_version from the list)
with data `{"source": {"kind": "file", "url": <returned url>, "name": "<id>.csv"}, "updated": {"at": <UTC time ending
in Z>, "by": "Quickplay run"}}`. Don't rewrite the page.

## Board schema (copy boards/hold/QD-028.json for the shape)
- `id`: next free QD-### across boards/queue, ready, done, failed, hold, rejected and reserve, never below `first_id` in
  config.json. `created`: today, YYYY-MM-DD. `format`: a format id. `category`: Gaming, Film, Music, Sport, Tech,
  Science, Entertainment (TV and anime go here).
- Optional (GitHub fills them when left out): `chipIcon` (a lucide icon name; set one only when it fits the topic better
  than the category's), `accent` (hex), `gap` (0.1), `tail` (0.6), `music.gain_db` (-15). Don't set a voice or caption style: GitHub gives
  every Short a look (caption style, voice and pace, camera energy, colour grade from templates/looks.json) and learns which
  looks keep viewers watching. Set `look` (e.g. {"captions": "pop"}) only when Charlie asks for one.
- `music`: {"mood": one of the `music_moods` in config.json, matching the topic's feel}.
- `beats`: one per sentence or two, 55 to 125 words in total (aim for 70 to 110).
  - `say`: the narration. `cap`: only if captions must differ in spelling, same word count as `say`.
  - `visual`: {"type": "none"} or a graphic:
    title {kicker?, lines[], highlight[indexes]} · stat {value, label, sub?} · cards {items[{icon, t, s?}]} ·
    quote {text, by} · date {month, day, weekday?, label, sub?} · versus {items[2 × {label, value, sub?}]} ·
    timeline {items[{y, t}]} · bars {items[{label, value, w (0 to 1)}]}. Add "atWord": n to reveal on the n-th word.
  - `impact`: true for a hit on the beat's first frame. Use on the hook and the payoff.
  - `shots`: 1 to 4 per beat, a new shot every 1.5 to 3 s. Fields: `src`, `w` (share of the beat), `at` (cut on word n),
    `focus` [x, y], `move` in|out|left|right|up|down|still, `label` {t, s} on a person's first appearance, `tin` flash for a reveal,
    `start` (seconds into a video), `cuts`: "auto" for trailers, `zoom`, `eq` ("gamma=1.5" to lift dark footage),
    `dark`: true only if a dark image is intended (otherwise near-black stock is skipped).
- `src` forms: `commons:File:Exact_name.jpg`, `commons-search:words`, `openverse:Full Name` (Creative Commons photos
  Commons lacks), `page:https://...` (an official page's own share picture; news outlets' pages are refused),
  `nasa:video:words`, `nasa:image:words` (NASA's public-domain library), `url:https://...` (official press or media
  files only, with `credit` and `source` on the shot), and stock: `pixabay:video:words`, `pixabay:image:words`.
- Real footage first (Charlie, 19 October): at least 4 in 5 shots show the actual subject, and always the hook. In order:
  the fact pack's real pictures, Commons photos of the people (`commons-search:Full Name`, with a `label` the first
  time each person appears; several shots of each person), `openverse:Full Name` when Commons has none, official press
  images and trailer files (`url:`) or an official page's picture (`page:`), and NASA photos and footage for space.
  Film and TV: official stills and short trailer moments under our narration, never long clips (a studio can claim the
  Short). Sport: photos of the players, managers and grounds, never match footage. Stock only when nothing real exists
  for that beat, at most 1 in 5 shots (the validator warns past that); stock queries are 2 to 4 concrete words that would
  be tags on the clip ("full moon night sky", not "mysterious feeling").
- `meta`: {title (under 50 characters ideally, 70 at most, one emoji at the end), summary (1 to 2 sentences),
  hashtags (8 to 15, most relevant first; #Shorts is added for YouTube), tags (5 to 15 search phrases),
  sources [[title, url], ...], facts [[claim, [source numbers]], ...], signals {source: [what the trend data showed]}}.
- `meta.comment`: one short question viewers can answer (under 100 characters, no links), posted as the channel's
  comment once the Short is public. `meta.alt_title`: a second title with a different angle (same rules as the title),
  used if the Short gets under half the usual views an hour after 24 hours.
- Optional: `flag` (see Approval), `publish_at` "YYYY-MM-DD HH:MM" (UK) for a fixed slot, `mode` "private" (test
  upload), "none" (render only) or "dry" (held for approval like a real Short, never uploaded).
