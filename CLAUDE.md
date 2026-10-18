# Quickplay daily script run

You write Shorts as JSON "boards" and push them. GitHub renders, checks, uploads and schedules them on YouTube, then
posts them to Instagram (automatically) and TikTok (as drafts Charlie posts). Two sessions a day: 06:50 UK writes most of
the day's Shorts; 12:50 UK writes the rest from fresher trends (breaking stories, things that took off this morning).
Spend as few tokens as possible: no rendering, no browsing beyond the sources you check, no recap messages.

## The goal
Monetisation as soon as possible. The YouTube Partner Program needs 1,000 subscribers and 10 million Shorts views in
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
- Topics with big audiences searching right now: gaming, film and TV, music, sport, celebrities, tech launches, space.
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
- TikTok takes only 5 drafts a day: set `"tiktok": true` on the 5 Shorts most likely to do well there (big fandoms,
  music, gaming, strong visuals, a surprise people want to share) and `"tiktok": false` on the rest. That is 5 across
  both runs: the 12:50 run counts today's boards already marked true (queue, ready, done) and marks only the rest.
  The same picks are the day's Instagram Reels (config instagram_mode "picks").
- Hashtags: 8 to 15, most relevant first (the first 3 show on YouTube, the first 5 go to Instagram, the first 7 to
  TikTok): exact names (person, title, team), then the franchise or show, the category, and 1 or 2 broad ones such as
  #Trending, #Gaming or #KPop. Never #viral, never anything unrelated. `meta.tags`: 5 to 15 phrases people would search.

## Facts (the part that matters most)
- Every factual claim needs two reputable sources that you opened in this session and that state it.
  Cite the exact page that states it, never a homepage or a search page.
- Good sources: the official source (publisher, studio, team, league, label, agency, NASA and the like) and
  established outlets (BBC, Guardian, Reuters, AP, The Verge, IGN, Eurogamer, Variety, Billboard, ESPN, Nature...).
  Aim for three: the official source plus two outlets. Cite the outlet's own site, never a site that reposts it.
  Wikipedia can be one of the two, never both. Never use forums, fan wikis, social posts or AI-written sites alone.
- Say what is new today. If the trending item repeats older news (a date announced weeks ago), lead with what changed.
- List each claim in `meta.facts` with the numbers of the sources (from 1) that confirm it.
- Dates, numbers and names: copy them exactly from the sources. If two sources disagree, leave the claim out.
- Can't verify it? Drop the claim, or drop the topic.

## Approval
`approval` in config.json: "all" means every Short waits for Charlie's OK; "flagged" means only flagged Shorts wait (the
rest upload straight away); "none" means nothing waits. Add `"flag": "<one line why>"` to a board when a human should
look first: a topic close to the excluded list, a person under 18 at the centre, heavy use of a brand's or someone's
footage, a claim you're less than sure about. Validator warnings and render checks (such as no real images) flag
automatically. Waiting Shorts sit in boards/ready with a private preview (draft release `preview-<id>`).
Reserve: evergreen Shorts written with `"reserve": true` render like any other but wait in boards/reserve (they never count
towards a day's capacity). Charlie approves them once ("reserve approve all", written to approvals/ as a line starting
with "reserve"), and GitHub uploads up to 2 of them only on a day when nothing new was written by 18:20.

## Steps
1. `git pull`. Read config.json, trends/latest.json (short on purpose), analytics/insights.md (the Recipe first), status/channel.json and
   status/ files changed in the last 2 days. Fix and re-queue anything in boards/failed/ worth saving (move it back to
   boards/queue/).
2. Capacity this session = the smallest of: `per_session`; `daily_limit` minus boards with today's `created` date
   (queue, ready, done and failed); `daily_limit` minus boards already in boards/queue/ and boards/ready/.
   On Sundays take one off (the weekly long video, pipeline/weekly.py, uses one upload). If it is 0, go to step 7.
3. Pick topics (see What gets views), starting with trends/requests.md: Charlie's own requests come first, then the
   trends; update that file in the same commit as the boards. Fill the rest of the day to match the Recipe in
   analytics/insights.md: its category mix for about 80% of the day (the other 20% on whatever trends hardest), and lean
   towards the formats, hook styles, title styles and lengths it lists. Breaking news still beats the mix. The 12:50 run
   looks for what has broken or grown since the morning (trends refresh at 11:35 UTC) and skips anything the morning run
   already covered. trends/research.json lists recent articles from
   reputable outlets and the Wikipedia page for each top trend: open those first and search only for what's missing.
4. For each topic: open the sources, choose a format, write the board, add hard names to `pipeline/pronounce.json`.
5. Run `python pipeline/validate.py boards/queue/<new files>` and fix every error. Warnings: fix them, or keep the
   board and add a `flag` saying why it is fine.
6. Commit all new boards in ONE commit to boards/queue/, push.
7. Lineup. Wait for GitHub to render (in the background, `git pull` every 3 minutes, up to 45 minutes, until each new
   board has a status/<id>.json). Then send Charlie ONE message, starting with the line `python pipeline/health.py`
   prints (fix or explain anything it lists):
   - approval "all": each Short in boards/ready as `QD-0xx · title · length · look` (status `look`: captions, voice,
     energy, grade, opening) with its hook line and any flags, then
     "Reply: approve all, approve all except QD-0xx, or reject QD-0xx." Attach the preview videos:
     `python pipeline/previews.py <scratch dir>` downloads them, then send the files.
   - approval "flagged": the same for flagged Shorts only; if nothing is flagged, one line naming what went out.
   - If analytics/decisions.csv has lines dated since yesterday, end with one line per change (at most 3):
     "From the data: <change>, because <why>."
8. When Charlie replies, put his decision on one line in approvals/<YYYYMMDD-HHMM>.txt (for example
   "approve all except QD-034"), commit and push. GitHub uploads approved Shorts within the daily limit and drops
   rejected ones. Reply in one line.
   Then TikTok: wait until the approved TikTok picks have a YouTube time (status publish_at, usually within 30 minutes).
   - `tiktok_mode` "inbox" (now): the drafts reach his TikTok phone app by themselves and the captions go on his TikTok
     queue page, https://claude.ai/artifact/Tc5EXtcFG77EUqvcbFKV1X (never in chat). Run
     `python pipeline/tiktok_files.py <scratch dir> --db`, ArtifactData `list` collection "tiktok" on that page, then ONE
     ArtifactData `batch`: `set` each printed Short not already listed (doc_id = its id, file_path = the printed file)
     and `delete` any doc with `"example": true` (if_version = its version). Then one line to Charlie, for example
     "TikTok: 5 drafts on their way to your inbox, captions on your TikTok queue." Don't rewrite the page.
   - `tiktok_mode` "manual", or Charlie asks for a video TikTok refused: run it without flags and send the video files
     and captions (for posting by hand).
9. Refresh the stats dashboard (see Stats dashboard). Finish with one line: how many Shorts and their titles.

## Stats dashboard
https://claude.ai/artifact/CErUUqubbPYWbVrN5XyhDy (private). GitHub refreshes analytics/ every hour (the full read three
times a day). Refresh the dashboard at the end of each run: Artifact `read` the dashboard; ArtifactData `list` collection
"datasets" (for each document's version); then for each dataset id that has a file, in order shorts, daily, progress,
hourly, drivers, decisions, geo, traffic, audience: Artifact publish with `url` (the dashboard), `file_path`
analytics/<id>.csv and `asset: true`; then ONE ArtifactData `batch` of `update` writes (collection "datasets", doc_id
<id>, if_version from the list) with data `{"source": {"kind": "file", "url": <returned url>, "name": "<id>.csv"},
"updated": {"at": <ISO time>, "by": "Quickplay run"}}`. Don't rewrite the page.

## Board schema (copy boards/hold/QD-028.json for the shape)
- `id`: next free QD-### across boards/queue, ready, done, failed, hold, rejected and reserve, never below `first_id` in
  config.json. `created`: today, YYYY-MM-DD. `format`: a format id. `category`: Gaming, Film, Music, Sport, Tech,
  Science, Entertainment (TV and anime go here).
- `chipIcon` (a lucide icon name), `accent` (hex), `gap`: 0.1, `tail`: 0.6. Don't set a voice or caption style: GitHub gives
  every Short a look (caption style, voice and pace, camera energy, colour grade from templates/looks.json) and learns which
  looks keep viewers watching. Set `look` (e.g. {"captions": "pop"}) only when Charlie asks for one.
- `music`: {"mood": one of the `music_moods` in config.json, matching the topic's feel, "gain_db": -15}.
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
- `src` forms: `commons:File:Exact_name.jpg`, `commons-search:words`, `pixabay:video:words`, `pixabay:image:words`,
  `url:https://...` (official press or media files only, with `credit` and `source` on the shot).
  Real images of the subject come first: official press and media-kit images (`url:`) and Commons photos of the people
  (`commons-search:Full Name`, with a `label` the first time each person appears). Several shots of each person.
  Stock is for mood and b-roll only, never the whole Short.
  Stock queries: 2 to 4 concrete words that would be tags on the clip ("full moon night sky", not "mysterious feeling").
- `meta`: {title (under 50 characters ideally, 70 at most, one emoji at the end), summary (1 to 2 sentences),
  hashtags (8 to 15, most relevant first; #Shorts is added for YouTube), tags (5 to 15 search phrases),
  sources [[title, url], ...], facts [[claim, [source numbers]], ...], signals {source: [what the trend data showed]}}.
- `tiktok`: true for the day's 5 TikTok picks, false for the rest.
- `meta.comment`: one short question viewers can answer (under 100 characters, no links), posted as the channel's
  comment once the Short is public. `meta.alt_title`: a second title with a different angle (same rules as the title),
  used if the Short gets under half the usual views an hour after 24 hours.
- Optional: `flag` (see Approval), `publish_at` "YYYY-MM-DD HH:MM" (UK) for a fixed slot, `mode` "private" (test
  upload), "none" (render only) or "dry" (held for approval like a real Short, never uploaded).
