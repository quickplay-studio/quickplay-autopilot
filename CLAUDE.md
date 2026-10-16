# Quickplay daily script run

You write the day's Shorts as JSON "boards" and push them. GitHub renders, checks, uploads and schedules them.
Spend as few tokens as possible: no rendering, no browsing beyond the sources you cite, no recap messages.

## Channel rules (non-negotiable)
- Quickplay Daily: anonymous, family-friendly, UK English. Topics people are searching for now.
- Never: politics, crime, health claims, money or investing advice, adult content, gambling.
- Explore the subject itself. Never talk about views, virality or "why it went viral".
- Every fact from at least two reputable sources you actually opened. No guesses; drop a topic you can't verify.
- No em dashes anywhere (titles, narration, captions, descriptions).
- Copy formats from templates/formats.json only. Never reuse another creator's footage or script.

## Daily steps
1. `git pull`. Read `trends/latest.json` (short on purpose), then `status/` files changed in the last 2 days.
   Fix and re-queue anything in `boards/failed/` worth saving (move it back to `boards/queue/`).
2. Capacity = 10 minus boards already in `boards/queue/`. Make at most that many.
3. Pick topics: strongest signal first (Google Trends traffic, YouTube views per hour, Wikipedia views,
   and `our_last_7_days` for what our viewers watch to the end). Skip anything covered in the last 14 days (titles in boards/done).
4. For each topic: open 2 to 3 sources, choose a format, write the board, add hard names to `pipeline/pronounce.json`.
5. Validate every board with `python -m json.tool`, commit them all in ONE commit to `boards/queue/`, push. Done.

## Board schema (copy boards/done/QD-028.json for a full example)
- `id`: next free QD-### across boards/queue, done and failed. `format`: a format id. `category`: Gaming, Film, Music, Sport, Tech, Science, Entertainment.
- `chipIcon` (a lucide icon name), `accent` (hex), `voice`: "F2" unless told otherwise, `gap`: 0.1, `tail`: 0.6.
- `music`: {"slug": one of pipeline/music/catalog.json, "gain_db": -15}, or leave out to auto-pick.
- `beats`: one per sentence or two, 2.5 to 3 words a second overall, 20 to 45 seconds total.
  - `say`: the narration. `cap`: only if captions must differ in spelling, same word count as `say`.
  - `visual`: {"type": "none"} or a graphic:
    title {kicker?, lines[], highlight[indexes]} · stat {value, label, sub?} · cards {items[{icon, t, s?}]} ·
    quote {text, by} · date {month, day, weekday?, label, sub?} · versus {items[2 × {label, value, sub?}]} ·
    timeline {items[{y, t}]} · bars {items[{label, value, w (0 to 1)}]}. Add "atWord": n to reveal on the n-th word.
  - `impact`: true for a hit on the beat's first frame. Use on the hook and the payoff.
  - `shots`: 1 to 4 per beat, a new shot every 1.5 to 3 s. Fields: `src`, `w` (share of the beat), `at` (cut on word n),
    `focus` [x, y], `move` in|out|left|right|up|down|still, `label` {t, s} on a person's first appearance, `tin` flash for a reveal,
    `start` (seconds into a video), `cuts`: "auto" for trailers, `zoom`, `eq` ("gamma=1.5" to lift dark footage).
- `src` forms: `commons:File:Exact_name.jpg`, `commons-search:words`, `pixabay:video:words`, `pixabay:image:words`,
  `url:https://...` (official press or media files only, with `credit` and `source` on the shot).
  Prefer real footage and photos of the actual subject over stock. Several shots of each person.
- `meta`: {title (under 70 characters, one emoji at the end), summary (1 to 2 sentences), hashtags (3 to 4 plus #Shorts),
  sources [[title, url], ...], signals {source: [what the trend data showed]}}.
- Optional: `publish_at` "YYYY-MM-DD HH:MM" (UK) for a fixed slot, `mode` "private" for a test upload.
