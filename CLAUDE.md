# Quickplay daily script run

You write Shorts as JSON "boards" and push them. GitHub renders, checks, uploads and schedules them on YouTube, then
posts them to Instagram (automatically) and TikTok (as drafts Charlie posts). One session a day at 06:50 UK (a second at
12:50 once `daily_limit` goes above 6). Spend as few tokens as possible: no rendering, no browsing beyond the sources you
check, no recap messages.

## The goal
Monetisation as soon as possible. The YouTube Partner Program needs 1,000 subscribers and 10 million Shorts views in
90 days, and the channel must get in before 1 February 2027 (after that, new channels need 20 million). That is roughly
110,000 views a day, so every Short has to earn its place. `analytics/insights.md` shows what is working: repeat it,
drop what isn't.

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

## Steps
1. `git pull`. Read config.json, trends/latest.json (short on purpose), analytics/insights.md, status/channel.json and
   status/ files changed in the last 2 days. Fix and re-queue anything in boards/failed/ worth saving (move it back to
   boards/queue/).
2. Capacity this session = the smallest of: `per_session`; `daily_limit` minus boards with today's `created` date
   (queue, ready, done and failed); `daily_limit` minus boards already in boards/queue/ and boards/ready/.
   If it is 0, go to step 7.
3. Pick topics (see What gets views).
4. For each topic: open the sources, choose a format, write the board, add hard names to `pipeline/pronounce.json`.
5. Run `python pipeline/validate.py boards/queue/<new files>` and fix every error. Warnings: fix them, or keep the
   board and add a `flag` saying why it is fine.
6. Commit all new boards in ONE commit to boards/queue/, push.
7. Lineup. Wait for GitHub to render (in the background, `git pull` every 3 minutes, up to 45 minutes, until each new
   board has a status/<id>.json). Then send Charlie ONE message:
   - approval "all": each Short in boards/ready as `QD-0xx · title · length` with its hook line and any flags, then
     "Reply: approve all, approve all except QD-0xx, or reject QD-0xx." Attach each preview video:
     `gh release download preview-<id> -p video.mp4 -D <scratch>/<id>` and send the files.
   - approval "flagged": the same for flagged Shorts only; if nothing is flagged, one line naming what went out.
   - Then the TikTok captions for today's Shorts, ready to paste: title, blank line, summary, blank line, the first 7
     hashtags plus #fyp. The TikTok drafts reach his inbox once each Short is scheduled.
8. When Charlie replies, put his decision on one line in approvals/<YYYYMMDD-HHMM>.txt (for example
   "approve all except QD-034"), commit and push. GitHub uploads approved Shorts within the daily limit and drops
   rejected ones. Reply in one line.
9. Refresh the stats dashboard (see Stats dashboard). Finish with one line: how many Shorts and their titles.

## Stats dashboard
https://claude.ai/artifact/CErUUqubbPYWbVrN5XyhDy (private). GitHub refreshes analytics/ three times a day. Once a day:
Artifact `read` the dashboard; then for each of analytics/shorts.csv and analytics/daily.csv, Artifact publish with
`url` (the dashboard), `file_path` and `asset: true`; then ArtifactData `update` collection "datasets", doc_id
"shorts" (or "daily"), data `{"source": {"kind": "file", "url": <returned url>, "name": <file name>},
"updated": {"at": <ISO time>, "by": "Quickplay daily run"}}`. Don't rewrite the page.

## Board schema (copy boards/hold/QD-028.json for the shape)
- `id`: next free QD-### across boards/queue, ready, done, failed, hold and rejected, never below `first_id` in
  config.json. `created`: today, YYYY-MM-DD. `format`: a format id. `category`: Gaming, Film, Music, Sport, Tech,
  Science, Entertainment (TV and anime go here).
- `chipIcon` (a lucide icon name), `accent` (hex), `voice`: "F2" unless told otherwise, `gap`: 0.1, `tail`: 0.6.
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
- Optional: `flag` (see Approval), `publish_at` "YYYY-MM-DD HH:MM" (UK) for a fixed slot, `mode` "private" (test
  upload), "none" (render only) or "dry" (held for approval like a real Short, never uploaded).
