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
- Charlie: full portrait videos with the text over the video, clear of the main feature. Layout "full" (replacing "face"
  in the test arms): the picture fills the screen, the 9:16 window on the person (the middle when no face is steady,
  vertical sources fill the screen as they are), and the text goes where the person is not: person high in the picture,
  hook and captions in the lower third; person low, hook and captions at the top; person in the middle, hook at the top
  and captions at the foot. Campaigns with full_frame rules (Speed's suitcase) keep letterbox.
- The scout ("scout" in requests/clips.txt, once WHOP_COOKIES exists): reads the Content Rewards discover pages signed
  in, judges every campaign page with the model against the channel's rules (clipping not UGC, YouTube allowed, footage
  provided, family friendly, open), ranks by rate times budget, writes status/scout.md and clips/scout.json; with
  VYRO_COOKIES it also saves Vyro's campaign list (status/scout_vyro.txt). Charlie joins the shortlist from his Mac;
  joining by GitHub comes after the first shortlist is reviewed.
- 22 October: the first run with the new arms made 11 clips (short arm, hook-first titles, one full layout, all
  fine). Two Flamingo hooks ("full psychological destruction", "generations of trauma") were legal but not family
  friendly: the planner now has a brand-safety rule, UNSAFE drops such hooks and titles at planning, and review() pulls
  a scheduled clip that carries one ("not brand safe"); a "go" run refilled the day.

## 22 October, 18:00 UK: better programmes, aligned with what people search
- Charlie: sign up to much better clipper programmes (N3on, the viral streamers of the moment) and align the choice with
  what people search on YouTube. Found: N3on's programme recruits on stream and Discord at $0.40 to $0.50 per 1,000
  (Nysos, Dexerto); the big streamer "clipper networks" (Adin Ross, Kai Cenat, xQc and others) are Discord invites with
  no public rates; several of the loudest networks (political and adult-adjacent creators) are off limits for this
  channel. Brand and creator campaigns on Content Rewards pay $1 to $6 per 1,000 for brand-safe footage, so they stay
  first; a streamer's own programme is joined when YouTube Shorts counts and the footage passes the profanity filter.
- The scout now ranks by rate times budget times (1 + heat), heat being the subject's Wikipedia page views over 7 days
  (Wikimedia REST, no key), presence in today's Google Trends, Wikipedia top pages and YouTube charts
  (trends/latest.json), the searches that already bring our viewers (analytics/search_terms.csv) and the count of
  YouTube search suggestions; status/scout.md shows the heat and why.
- The planner reads the subject's live YouTube search suggestions (clips.searches) and prefers the moments those
  searches want, using their words in hooks and titles.

## 22 October, 19:00 UK: the Mac worker, the streamer radar, channels per niche
- Charlie: "set it up so that you can run within Chrome and do different things on different websites". The cloud
  sessions have no browser; the scheduled task "Quickplay: Chrome jobs (on the Mac)" runs on his Mac with Claude in
  Chrome every day at 19:07 UK and whenever a cloud session fires it: it works through docs/CHROME_JOBS.md (cookies,
  joins, account keys, new channels) and asks him only for passwords, codes and accounts he must create. One approval
  from him binds it to the Mac ("Require this computer").
- The streamer radar: clips/streamers.json (the viral streamers and creators, with their programme and any reason they
  are off limits) is scored by heat() in every scout run and written to status/streamers.md with "Programmes to join
  next"; the scout runs on GitHub every morning at 09:35 UK, so the evening's Chrome jobs always have a fresh list.
- More YouTube channels for more niches: each campaign names its channel ("channel", default "clips"); each channel
  has its own learned ceiling (clips/state/ceiling_<name>.json), its own daily number and shares (allocate per
  channel), its own sign-in (tokens/youtube_<name>.enc) and its own Instagram and Facebook secrets
  (IG_<NAME>_*, FB_<NAME>_*, read from the workflow's secrets without a workflow edit). Adding a channel is a Chrome job.
- Charlie: every YouTube channel under the studio Google account, each signed up to every campaign, each with automatic
  clips and submissions. Done in the code: a campaign lists its channels ("channels": clips, gaming, irl), each channel
  gets different moments of the same footage (a moment carries its channel), its own number, ceiling, sign-in
  (tokens/youtube_<name>.enc; the sign-in recognises the channel by its title: Gaming, IRL, Clips), social accounts and
  submit rows (a "channel" column). Channels without a sign-in are skipped. One Content Rewards account and one Vyro
  account hold all the channels as connected accounts (a second clipper account would count as linked accounts and be
  banned). Creating the channels is Charlie's (a Chrome job asks him); signing them in and connecting them is the worker's.

## 22 October, 19:30 to 20:10 UK: the Mac run, the real forms, GitHub's hold
- What Claude cannot do in Charlie's Chrome, learnt today: click an extension's popup (the cookie export), type any secret,
  key or cookie text into GitHub, type a password, create an account, or click anything on accounts.google.com (the
  extension refuses the domain, so every YouTube Allow, including Content Rewards' and Vyro's channel connects, is his).
  docs/CHROME_JOBS.md "Who does what" has the split; each run asks him for his part in one message with links.
- The submission forms as they really are (pipeline/submit.py): Content Rewards opens a dialog with one url box, three
  checks (a linked account, not already submitted, posted within the last 30 minutes), a consent box and Submit clip; a
  refused check shows a Failed icon beside its reason. The 30-minute rule means only the 18:01 batch run can submit that
  day's clips; anything older is marked "failed: past the 30-minute window" once and never retried. Vyro's Add Posts page
  lists the joined campaigns as cards (each campaign's card text is "card" in campaigns.json), each with its own Submit
  post; then Use a link instead, the social account (the YouTube channel), "This account can submit N posts today" (5 per
  connected channel a day, so three channels give 15 Vyro submissions a day), the rules box, Continue, Review your post
  (ad disclosure, hashtags, collaborators), Submit post. Duplicate answer: "Post not submitted. You have already
  submitted this post to a campaign." Seven of the 21 October clips were already pending on Vyro by hand.
- GitHub held every clips run from 19:01 UK as "this workflow file may be malicious": clips.yml passed toJSON(secrets)
  into one variable (so IG_<CHANNEL>_* needed no workflow edit). Each channel's four Instagram and Facebook secrets are
  now named in clips.yml; a new channel means adding its four lines. Charlie approved the held run (#41).
- Channels: Quickplay Gaming Clips and Quickplay IRL Clips exist and are signed in (tokens/youtube_gaming.enc and
  youtube_irl.enc). Unverified: one phone number verifies two YouTube channels a year and Daily and Clips used it, so
  they run at the lower daily number until their history earns advanced features.
- Campaigns: joined Kevin Langue's Vyro campaign (clips and irl). Not joined, with reasons, in docs/CHROME_JOBS.md.

## 22 October, 20:10 to 21:00 UK: Vyro from the Mac, one Instagram, the identity guard
- Vyro drops the saved session the moment it arrives from GitHub's servers (the probe showed vyro_sid given and gone;
  Content Rewards accepts its own), and disguising the headless browser would be working against Vyro's clipper terms,
  which count automated posting as spam. So Vyro clips go public at 19:00 UK (campaigns.json batch_times) and the Mac
  Chrome run at 19:07 UK submits them in Charlie's own browser (docs/CHROME_JOBS.md standing job); GitHub leaves Vyro rows
  alone (submit_by mac) and submits Content Rewards itself at 18:01, inside its 30-minute window, with a random 2 to 5
  minute gap before each submission (Charlie: never a burst the second the batch goes live).
- The two campaign-site sign-ins live encrypted in tokens/login_whop.enc and tokens/login_vyro.enc (logins.yml writes
  them from the pasted secrets WHOP_COOKIES and VYRO_COOKIES); the clips workflow no longer reads the secrets, which was
  what GitHub held as "possibly malicious" (every clips run needed Charlie's Approve and run until then).
- Charlie: one Instagram account, his existing clipping one, takes every kind of clip; no more Instagram accounts. A
  channel without its own IG_<CHANNEL>_* secrets uses the clips channel's (clips.py accounts). Caps: Vyro 5 submissions
  a day per connected account, social_per_day Reels a day. He adds IG_CLIPS_TOKEN and IG_CLIPS_USER_ID from the studio
  Meta app (Instagram Login); the clips line skips Facebook.
- Charlie: nothing outside the studio Google account, ever, and a flag if anything else is touched. The identity guard
  (pipeline/identity.py, audit.yml every 6 hours) resolves every sign-in live against config.json "accounts" (listed ids,
  the Quickplay name rule, the secrets allowlist, own-site cookies only, expected token files); first audit clean, 30
  checks. A mismatch opens the issue "🔒 Security: a sign-in outside the studio account" and the gate step at the top of
  clips, social, publish and engage stops posting until the next clean audit. The Mac run checks the Chrome profile's
  Google account first. A new secret goes on the allowlist by hand, on purpose.
- Charlie says yes to approving held runs: they are his own workflow, read line by line; nothing leaves except to the
  campaign sites, YouTube, Meta and the repo.

