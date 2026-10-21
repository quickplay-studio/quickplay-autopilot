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

## Built 21 October (01:00 to 02:30 UK)
- clips/campaigns.json: speed-expedia active (Reach, $1 per 1,000 on YouTube, 10,000 views before pay, footage = the
  Expedia Unpack segment 3:56:30 to 4:12:22 of the 14 October stream, Google Drive file in the rules), forgegui-roblox
  joined but off (an advert for a tool that wants its own Roblox account).
- pipeline/clips.py + clips.yml: source (gdown the Drive file to /mnt/clips, cut and shrink the segment once, keep it as
  release asset clips-src), plan (faster-whisper small on the CPU, Gemini picks moments that keep the rules), make
  (ffmpeg: picture centred over its blurred copy, hook and destination label on top, captions below, credit at the foot,
  loudness normalised), upload (private, public together at 18:00 UK; CLIPS_MODE=private for a watchable test), stats
  (clips/stats.csv). Charlie's part: at 18:00 paste each link from clips/submit.csv into its campaign.
- Test by pushing requests/clips.txt with "test 2"; the daily run is 13:00 UK; "stats" refreshes the numbers.
- Still to do: a Whop API or scraper for submissions does not exist, so submission stays manual; Vyro campaigns once
  Charlie sends them; a second source kind for Twitch (TWITCH_CLIENT_ID and secret) when a campaign needs it.

## Live from 21 October
- Footage: Google Drive (gdown) and Frame.io share links (a headless browser presses Download, Download in Browser,
  Original); each source is cut to 720p once and kept as a release asset (clips-src). Sources cached: speed-expedia,
  mrbeast-cod, tdr-stinkyasher, tdr-mitch, tdr-flamingo, tdr-jenny, valorant-champs.
- Day: 10:00 UK prepare (sources, transcripts, moments), 13:00 UK make and upload (daily_clips 10, shared by expected
  money, per_day 3 a campaign), public together at 18:00 UK, stats 23:30 UK. Charlie pastes the links at 18:00 from
  https://quickplay-studio.github.io/quickplay-autopilot/submit.html (Content Rewards: Submit clip; Vyro: Add Posts).
- Guards: no strong language (the planner drops the moment; a scheduled clip that fails is pulled to private before
  it publishes), no black pictures (same), long picks cut to the limit, a frame of every clip in clips/frames.
- First day: 10 clips across 7 campaigns scheduled for 18:00 UK (2 pulled for swearing, 1 for a black screen,
  replaced).
- Off and why: clips/campaigns.json (why_off). SEGA Metaphor waits for Charlie's audience screen recording.

## 21 October, 10:00 to 12:30 UK
- Series campaigns (rules "series"): a folder share downloads as a zip (or one file), every file is shrunk and joined in
  order, and plan_parts() posts each episode whole as Part 1, 2, 3 (cut at sentence ends, never over max_s, never a
  short tail). VALORANT microdrama is on (its share holds Episode 2 only).
- The clips channel's own learning ceiling (clips/state/ceiling.json): from daily_clips 10, +2 after each full day
  with no refusal, settles where YouTube refuses; upload() reports uploadLimitExceeded to it.
- Campaigns switch themselves off (check_campaigns, every prepare and run): past their end date (ends, from the
  capture), or when their Content Rewards page, read rendered, says full or ended or shows under $50 remaining; the
  figure read is kept as budget_left (Speed: $1,539 on 21 October). Vyro pages need a login, so Vyro goes by end date.
- Model answers wrapped in a list are read; "prepare <campaign>" and "prepare redo <campaign>" in requests/clips.txt
  target one campaign or rebuild its source.

## 21 October, 12:00 to 14:00 UK: the tactics of the big clipping channels, built in
- Layouts as a test on every clip: letterbox (the picture over its blurred copy), face (a 9:16 window following the
  face), split (the cam on top, the whole picture below). OpenCV finds faces every 2 seconds; the group of detections
  present in half the frames that changes most over time wins (a wall never talks). A campaign rule full_frame (Speed:
  the suitcase must stay in frame) and vertical sources keep the whole picture.
- Captions as a test: lines (four words at a time) or karaoke (each word lights up yellow as it is said).
- Punch-in as a test: a 1.5-second 1.12x zoom of the picture on the peak the planner names.
- clips/insights.json (from stats): each test's median views per arm (24 hours old, 3 clips an arm) and the best arm,
  which test_plan() then picks 70% of the time; the campaigns' medians feed the daily shares.
- Instagram Reels, Facebook Reels and TikTok for every public clip at the batch time (social_posts: IG_CLIPS_TOKEN,
  IG_CLIPS_USER_ID, FB_CLIPS_PAGE_TOKEN, FB_CLIPS_PAGE_ID, tokens/tiktok_clips.enc; social_per_day a platform), each
  post its own row on the submit page (campaigns pay per platform). The clip files are kept as release assets
  (clips-out) so the later run can post them.
- Comments: the planner's question as the channel's comment on every public clip, and part links between the parts
  of an episode (engage(), in the social and stats runs).
- A campaign may name its channel ("channel": "clips" by default, tokens/youtube_<channel>.enc); batch_times can give
  a platform its own batch time (Vyro at 22:00 UK, say).
- Requests: "test 1 layout=split tdr-mitch" forces an arm on named campaigns, privately.

## 21 October, 18:00 UK: the first batch is live
- 11 clips public at 18:00 UK across 6 campaigns (4 of the day's uploads pulled to private by the guards), the clips
  channel's limit now 12 a day. The submit page lists the last 3 days only.
- A clip planned before the planner asked for a comment question gets one at comment time (question_for: the model
  reads what was said in the clip; a plain question when no model answers). hours_public counts from the publish time,
  not the upload, so the 24-hour insight reads true.

## 21 October, 19:00 UK: GitHub submits the links itself
- Charlie: "automated with submitting the clips" (he cannot always be at his phone within 30 minutes). Neither platform
  has a clipper API, so pipeline/submit.py is a headless browser with the studio account's saved logins (secrets
  WHOP_COOKIES for contentrewards.com and whop.com, VYRO_COOKIES for app.vyro.com: the cookies.txt that the "Get
  cookies.txt LOCALLY" extension exports). It runs at the end of every batch and stats run and on "submit" in
  requests/clips.txt ("submit probe": a login check only): the campaign page, Submit clip (Content Rewards) or the
  add-clips page, the campaign, Submit post (Vyro), the link, confirm, the page's answer. Rows get the time submitted or
  "failed: why" (tried again next run, screenshot status/submit_<site>.png, the page's buttons in the log). An expired
  login raises a GitHub issue with the export steps and closes itself when a submission works. The phone page now lists
  only what GitHub could not do. Batch crons moved to minute 1 (GitHub starts the hour's runs late).
- Content Rewards' clipper terms count views from the submission, so a late link loses views; that is why this matters.

## 21 October, 19:30 UK: the dashboard, two more form tests, the day's number filled
- Charlie: maximum uploads to maximum campaigns; a campaign dashboard of all money and all views; the footage is fixed,
  so the Shorts change in their form. docs/clips.html (https://quickplay-studio.github.io/quickplay-autopilot/clips.html):
  money estimated per campaign (views over its minimum times its rate, capped), views, clips, submissions, budget and
  end dates, which form wins per test, and every clip; read from clips/stats.csv, campaigns.json and submit.csv.
- Two more tests on every clip: length ("short": the same moment cut at its first sentence end after the peak, inside
  28 seconds, when that saves over 4 seconds) and title ("hook first": the hook as the title, the subject after).
  Stats and insights pick them up as test_length and test_title; the dashboard adds length and hook-word bands.
- The day's number is filled: after per_day each, campaigns take one more in turn up to per_day_max (8) until the
  limit is met (series campaigns stay at per_day). The ceiling rises 4 a day (clips_limit_step) up to 60.
