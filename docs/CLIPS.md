# Quickplay Clips: a second channel of permitted clips, fully automated

Charlie, 21 October (00:30 UK): a new YouTube channel for clipping only, run alongside Quickplay Daily, fully automated,
clips made from viral and brand-new content from any creator's source, not only YouTube. Total control given on how to
make, upload and grow it.

## The one rule that makes the money real
A clip is used only when its creator has said yes: a clipping campaign (Whop "content rewards" and the like) or a
creator's own clipping programme. Those pay per 1,000 views, which is the clip channel's income (a channel of other
people's footage is "reused content" to the Partner Program, so YPP is not the plan there; the main channel carries
YPP). Permission is also what keeps copyright strikes away; Content ID claims on music in a stream are harmless to a
campaign payout. A source with no permission record is never fetched. Nothing is downloaded from a platform that
forbids it for that creator's content.

## What Charlie sets up (all free)
1. The channel: YouTube, switch account, "Create a channel" under the studio Google account (a brand channel, for
   example "Quickplay Clips"): https://www.youtube.com/account then "Add or manage your channel(s)". Phone-verify it
   for advanced features: https://www.youtube.com/features
2. Sign the channel in: the hourly social workflow keeps a sign-in link in status/youtube_connect.json; open it while
   using the clips channel, paste the code into the social workflow with youtube_channel "clips"
   (https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/social.yml, Run workflow). The token is
   stored encrypted as tokens/youtube_clips.enc. Same Google Cloud project and OAuth client as the main channel (the
   API allowance is shared; a second project later if it runs short).
3. Campaigns: join 3 to 5 clipping campaigns that allow YouTube Shorts and give footage (a Drive or Dropbox folder of
   raw footage, or a Twitch, Kick or YouTube channel to clip): https://whop.com/discover/ (search "clipping" or
   "content rewards"); creators' own Discord clipping programmes count too. For each one send: the campaign link, the
   creator, where the footage comes from, the rules (required caption, hashtags, credit, length, what is off limits),
   the payout per 1,000 views, and how clips are submitted (a link form, or a connected account). They go into
   clips/campaigns.json (no secrets in it).
4. Twitch API (for Twitch sources; free, no user sign-in): https://dev.twitch.tv/console/apps, "Register Your
   Application" (category Other, redirect http://localhost), copy the Client ID and a Client Secret into the repository
   secrets TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET:
   https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new
5. Kick API (only for Kick sources): https://kick.com/settings/developer, create an app, secrets KICK_CLIENT_ID and
   KICK_CLIENT_SECRET.
6. Optional: a second free Gemini key from a second AI Studio project (its own free quota, so the clips line never
   competes with the Shorts line): https://aistudio.google.com/apikey, secret GEMINI_API_KEY_CLIPS.
7. Payouts: the campaign platform's payout settings are Charlie's own (never touched by the automation).

## How the line will work (pipeline/clips.py, .github/workflows/clips.yml)
- clips/campaigns.json: one entry per campaign: name, creator, source {kind: twitch | kick | youtube | drive | release,
  id or url}, rules {caption, hashtags, credit, min_s, max_s, avoid}, payout_per_1k, submit {kind: link_form | auto,
  url}, active.
- Every 2 hours: for Twitch and Kick sources, the official clips of the last 24 hours with their view counts (the
  audience has already chosen the moment); for Drive, Dropbox and release footage, the files not used yet; for a
  YouTube source, the creator's newest videos (downloads from YouTube are unreliable from GitHub's servers, so campaigns
  with a footage folder come first). The strongest unused moments by views an hour win; long footage is transcribed on
  the runner (faster-whisper, CPU) and Gemini marks the moments worth a clip.
- Make: ffmpeg cuts 15 to 50 seconds, reframes to 9:16 (a vertical clip as it is; a landscape one centred over a
  blurred copy), burns word-timed captions, a hook line at the top (Gemini, under 8 words), the creator credit badge,
  normalised sound; the description carries the campaign's caption, hashtags and credit word for word.
- Upload: the clips channel, in learned slots like the main channel, inside the shared API allowance (quota.py);
  the title is the hook plus the creator's name; the campaign's required text is never shortened.
- Learn: the same analytics as the main channel (views, retention, swipe-away) by campaign, creator, source, length,
  caption style and hook style; the next picks follow the data; clips/payouts.csv tracks what each campaign owes.
- Submit: clips/submit.csv lists each new clip's link and campaign for the ones that need a form; campaigns that track
  a connected account need nothing.
- First week on private uploads for one campaign, then public.
