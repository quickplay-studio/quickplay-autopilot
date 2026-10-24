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
- Charlie (22 October, 22:50 UK): the Instagram account for the clips is quickplaydaily itself, the main channel's,
  already signed in (tokens/instagram.enc); no new account, no new token. clips.py accounts() falls back to that sign-in
  when no IG_CLIPS_* or IG_<CHANNEL>_* secrets exist. The Daily Shorts and the clips share its daily Reels number
  (Instagram allows 100 API posts a day; the ramps keep it far below). He connects quickplaydaily on Content Rewards and Vyro.
- Charlie (22 October, 22:55 UK): "update me when any money is made". alerts.py money() runs with the evening check
  (21:30 UTC): the clips' estimated earnings (the money page's sum: views over each campaign's minimum at its rate,
  capped per clip) are noted in one GitHub issue, "💰 Money: the clips have earned about $X so far (estimate)", updated
  whenever the figure has risen by a dollar or more (status/money.json remembers the last note); the Partner Programme
  thresholds (1,000 subscribers; then both) get their own issue once. The GitHub app on his phone shows them. The
  platforms' own earnings pages are the truth; payouts need a payout method set on Whop and on Vyro, his to do.

## 22 October, 23:55 UK: minimums that our clips can reach
- Charlie: favour campaigns our clips can actually earn from. clips.reach_share(min_views) is the smoothed share of our
  measured public clips (24 hours or more) at or over a minimum, (reached + 1) / (measured + 4), floor 0.05, 1.0 with no
  minimum; allocate() multiplies each campaign's expected money by it.
- The scout's model wrote "min views 0" for every campaign; submit.cr_terms() now reads each platform's rate, minimum
  payout and cap from the page (minimum views = minimum payout / rate x 1,000) and any spent per-platform budget, and a
  campaign whose YouTube share is unpaid or spent no longer fits. Briefs and footage are only visible after joining, so
  the Mac run checks those after it joins (docs/CHROME_JOBS.md).
- Checked tonight and not used: Pet Simulator 99 (wants original drama commentary, no footage), CLASH x HOH (a support
  ticket with analytics for every clip; 40% of views from US, UK, CA, AU), YoungLA (YouTube budget spent), Stranger Than
  Heaven (crime theme).

- 23 October night (Charlie: clips longer and likely to go viral). 51 public clips, up to 66 hours old, have 4 views at most, so the length and layout "tests" were deciding on nothing: insights() picked the first arm on a 0 to 0 tie (letterbox). Now a verdict needs a mean of 20 views and a 10% lead; stale verdicts cleared. The planner uses the best free models (writing order, never Claude), is told what makes a clip go viral (a grab in the first 2 seconds, no context needed, one payoff, ends on it), scores each moment 1 to 10 and keeps 6 or more, best first; already-clipped transcript lines are marked so it stops re-picking them (8 of 8 picks were overlaps). Clips run 25 to 75 s (every campaign, MIN_S/MAX_S); the "short" length arm is retired.
- 23 October night: 16 made clips were stuck and 12 uploads refused today, all on Quickplay Gaming Clips and Quickplay IRL Clips (unverified: Charlie's one number already verified Daily and Clips). clips.upload() now hands a clip refused for the daily limit to the campaign's other channels, then Quickplay Clips (verified), and marks its channel; the stuck ones go out on the next run.
- 23 October night: found why the clips have never earned. clips.yml compared the batch-time schedule to "1 17,18,21,22 * * *" while the cron was "1 17,18,19,21,22 * * *", so the social branch never ran: 0 clips posted to Instagram, Facebook or TikTok and 81 of 91 YouTube clips never submitted to a campaign (those runs made more clips instead). GitHub also starts crons up to 30 minutes late, past the 25-minute window. Now: cron 16:31 and 17:31 UTC; the job waits for 19:01 UK when the batch is under 100 minutes away (either side of the clock change) and posts and submits then.
- 23 October night: "viral" is now measured, not just claimed. Each moment keeps the planner's 1 to 10 score; stats.csv records it; insights() compares it with real views (score_bands: under 6, 6 to 7, 8 to 10) and learns min_score (the cut whose clips average the most views, 10 clips either side, 20 views or more, 1.2x the rest); plan() uses it in place of 6.
- 23 October night (Charlie: more sources to confirm a trend). submit.heat() adds a sixth independent signal: how often a subject is in the day's top posts on r/LivestreamFail, r/Twitch and r/KickStreaming (free RSS), up to 0.8. Other clipping platforms worth Charlie joining himself (Claude never makes accounts): Klippify, Vues, Clipping Culture on Whop; the scout reads a platform once it is joined.
- 23 October night (Charlie: every clip gets our own take, so it is commentary, not a re-upload, under YouTube's 1 October rule). The planner writes an intro (6 to 12 words, our set-up, no spoiler) and an outro (our reaction and a question for the comments) with each moment (take_lines() writes them for moments planned earlier; opinion and framing only, checked for profanity and brand safety). make_clip(): the house voice (Chatterbox F2, as the Daily Shorts) reads the intro over the first seconds with the stream's sound dipped to 25%, and the outro on a held last frame (about 3 to 4 s) with the line on screen; a campaign whose rules avoid AI-made video (speed-expedia) gets the take as on-screen text only. Series parts keep no take. Recorded as test "take" (voice, text, none) in stats.csv. clips.yml installs the voice only for the clip-making runs.
- 23 October night: campaign clips are paid per view, so UK advertising rules (ASA CAP code, CMA influencer guidance) want "#ad" up front and YouTube wants the paid promotion box: every clip description and Instagram caption now opens with #ad and ends with "Paid clip: we are paid per view by the campaign.", and uploads set paidProductPlacementDetails (dropped, keeping #ad, if YouTube refuses the part).
- 24 October, overnight: the spoken take works on GitHub. The private test (run 40027918262) made 11 clips: 9 with the house voice reading our intro and outro, 2 (speed-expedia, which avoids AI) with the take as text. A "private 1" test makes one clip per campaign per channel, so those 11 good clips would have stayed private and wasted; new command "promote" (requests/clips.txt) schedules the last 48 hours' private test clips into the next batch on YouTube (publish time set, counted in the channel's day so the next run makes that many fewer, submit rows given the public time). Run once tonight for these 11. Resilience: the same job's installs stalled 37 minutes on a slow package mirror, so apt now retries with time limits, the browser install has a time limit with its plain fallback, and clips.py stops starting new campaigns 135 minutes after the job began (JOB_T0), so the Save step always runs before the 170-minute stop.
- 24 October, overnight: long streams are planned a window at a time. valorant-champs is 144 minutes (27,757 words) and the planner sent all of it in one prompt; nothing came back. Now a transcript over 9,000 words goes in windows of about 9,000 (13,000 tokens), the one with the least already clipped first, so each run plans fresh minutes and the free models' size limits are never hit. Together with the empty-reply fix (docs/NEXT.md), valorant-champs and kevin-langue-ghost should make clips again.
- 24 October, overnight: a place a campaign leaves unfilled (nothing left to clip, no moments found, a failure) now goes to the campaigns on the same channel that filled theirs, strongest first, one more each round while time lasts (clips.spill). Last night the finished Valorant series and the two campaigns with no moments left 3 of the day's places empty.
- 24 October, 00:50 UK: the promote run was held back by the YouTube allowance guard (7,666 units spent in YouTube's day, 3,400 kept for the day's uploads), which is right: it never spends what uploads need. A held-back promote now leaves clips/state/promote.json and the next run or prepare after YouTube's reset (08:00 UK) finishes it; the 10:00 UK prepare run will schedule the 11 take-test clips into the 19:00 batch.
- 24 October, overnight: the irl and gaming channels' learned limits were wrong. A refusal settled the ceiling at the clips scheduled for the next batch, which after 18:00 UK is tomorrow's batch (0), so channels refused after 10 uploads each learned a limit of 4 and would have made 6 fewer clips a day each. A refusal now settles it at the clips YouTube took on that channel in the last 24 hours (uploads_24h); both ceilings set to 10 by hand from yesterday's uploads.
- 24 October, overnight: the clips are barely being shown. 34 public clips on the clips channel had 11 views in all (median 0 after 30 hours); gaming 20 views on 7, irl 0 on 10. A Short normally gets a few hundred test views, so this is distribution, not quality. The nightly stats now record YouTube's own verdict on every clip (upload status, rejection reason, countries blocked: a copyright claim usually shows as blocked countries, age restriction, made for kids), clips/reach.json sums them per channel, the hub's clips tile shows any verdicts, and alerts.py opens "📉 YouTube is showing the clips to almost nobody" with what to read in Studio when 8 or more day-old clips on a channel are 80% unseen or any are rejected or blocked. A stats run was started tonight to read the verdicts.
- 24 October, 01:20 UK, the first verdicts: YouTube has not rejected, blocked, age-restricted or marked for kids a single clip. So the clips are clean and simply not being shown: 17 of the clips channel's 23 day-old clips have no views, 11 views in all. That points at originality (the 1 October rule: reposts with little change lose reach to the original) and at brand-new channels, not at copyright. The spoken take started tonight is the answer to the first; the reach check now calls a channel unseen at 70% with no views or under 5 views a clip, so the alert fires on today's numbers. If clips with the take are still unseen after two days, the next test is fewer clips a channel a day.
- 24 October, overnight: the next test runs itself. reach_check now also scores the clips with our own take on their own; when 8 or more of them on a channel are a day old and still 70% unseen (or under 5 views a clip), that channel makes clips_unseen_cap (4) clips a day instead of its learned ceiling until YouTube shows them, with one line in analytics/decisions.csv. Fewer clips cost less of the shared YouTube allowance and look less like a new channel's spam burst; the cap lifts by itself when the reach check clears.
- 24 October, 10:50 UK: the held-back promote ran in the 10:24 prepare run with a 72-hour window (written by hand last night), which reaches back to 21 October and also took about 20 older private test clips (no spoken take, an unfinished Valorant series among them) into tonight's batch, on top of the 11 take clips meant. New command "demote <time>" puts promoted clips uploaded before that time back to private (YouTube, plans, submit rows); "demote 2026-10-23T22:00+00:00" queued behind the prepare run, so tonight's batch is the 11 take clips plus the day's new ones. promote now takes a "since" time and never promotes series parts.
- 24 October, 14:40 UK: pre-flight for tonight's first real submission run: the Content Rewards sign-in works (dry probe: logged in, Submit clip found on all 4 due rows); Vyro is the Mac's job (submit_by mac) and had 44 rows waiting. Vyro takes 5 posts per connected account a day, so 15 a day across the three channels, but the 13:00 run made 39 Vyro clips for tonight: most could never be submitted, so they could never earn, while they spent the YouTube allowance and flooded the channels. Now a channel makes no more of a site's clips a day than the site accepts (campaigns.json submit_daily_limits, Vyro 5; allocate and spill both respect it), and its other places go to campaigns on sites without a daily limit. The Mac job submits newest first (the day's clips carry the spoken take) and skips rows over 48 hours old when the day's rows fill an account's 5.
