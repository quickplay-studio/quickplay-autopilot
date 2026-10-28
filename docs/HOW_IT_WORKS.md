# Quickplay autopilot

Makes and schedules Quickplay Daily Shorts on GitHub's free runners. Claude only writes the scripts.

## How a Short gets made
1. A script ("board") is committed to `boards/queue/`. Formats live in `templates/formats.json`.
2. The `render` workflow picks up to the daily upload limit, gives each a posting slot (config.json: 24 a day from 07:30 UK, every 40 minutes, until the times learned from results take over), then for each one:
   fetches media (Wikimedia Commons, Pixabay, official press files), records the narration (Chatterbox, MIT licence),
   renders the video, and runs checks (length, narration clarity, scene cuts). Every Short has a video playing softly
   blurred behind it (2 to 4 stock clips from Pexels, then Pixabay, matched to the topic by the board's `background`
   searches, never the same clip twice in a week); photos sit on top as cards, real video of the subject plays full screen.
3. A separate job uploads and schedules it on YouTube. The render job never sees the YouTube keys.
4. Results land in `status/` and `review/` (a frame from every shot), and the board moves to `boards/done/` or `boards/failed/`.

The `trends` workflow writes `trends/latest.json` every morning for the script writer.

## Secrets (Settings, Secrets and variables, Actions)
`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `PIXABAY_API_KEY`, `PEXELS_API_KEY`, `MUSIC_KEY`.
Cut GitHub off from YouTube at any time: myaccount.google.com/permissions, Quickplay Uploader, remove access.

Music is from YouTube's Audio Library and is stored encrypted so it isn't redistributed.
