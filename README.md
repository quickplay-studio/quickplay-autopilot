# Quickplay autopilot

Makes and schedules Quickplay Daily Shorts on GitHub's free runners. Claude only writes the scripts.

## How a Short gets made
1. A script ("board") is committed to `boards/queue/`. Formats live in `templates/formats.json`.
2. The `render` workflow picks up to the daily upload limit, gives each a posting slot (09:00 to 22:30 UK, every 90 minutes), then for each one:
   fetches media (Wikimedia Commons, Pixabay, official press files), records the narration (Chatterbox, MIT licence),
   renders the video, and runs checks (length, narration clarity, scene cuts).
3. A separate job uploads and schedules it on YouTube. The render job never sees the YouTube keys.
4. Results land in `status/` and `review/` (a frame from every shot), and the board moves to `boards/done/` or `boards/failed/`.

The `trends` workflow writes `trends/latest.json` every morning for the script writer.

## Secrets (Settings, Secrets and variables, Actions)
`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `PIXABAY_API_KEY`, `MUSIC_KEY`.
Cut GitHub off from YouTube at any time: myaccount.google.com/permissions, Quickplay Uploader, remove access.

Music is from YouTube's Audio Library and is stored encrypted so it isn't redistributed.
