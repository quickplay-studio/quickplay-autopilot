# Chrome jobs: what the Mac session does in Charlie's browser

The cloud sessions and GitHub cannot click in Charlie's Chrome. The scheduled task "Quickplay: Chrome jobs (on the Mac)"
runs on his Mac with Claude in Chrome (daily at 19:07 UK, and whenever a cloud session fires it with new work). It reads
this file, does every job marked **open** in order, asks Charlie only for passwords, codes and accounts he must create
himself, then marks each job **done** (with the date and a line on what happened) or **blocked** (why, and what Charlie
must do), commits as "Quickplay Studio" and pushes. Rules: CLAUDE.md (studio account only, never type passwords, keys
only in GitHub secrets, family friendly, UK English, no em or en dashes). New jobs go at the top of the list, newest
first; the task text of a fired run counts as an extra job.

## Who does what (learnt 22 October)
Claude in Chrome acts inside web pages only, and Claude never handles credentials. So in every job:
- Charlie's hands: clicking an extension's toolbar icon or popup (the cookie export), pasting any secret, key, token or
  cookie text into GitHub (https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new), typing a
  password or code, creating an account (YouTube channels, Instagram, Facebook, Cerebras, Mistral), and clicking Allow on
  an OAuth or Connect screen. The run opens the page for him, asks in one message with the exact steps and links, and waits.
- Claude's hands: everything else on a page (joining campaigns, reading rules, forms without credentials), pushing
  requests (requests/clips.txt), reading the run results, fixing pipeline/submit.py, editing clips/campaigns.json, the
  social workflow runs, and this file.
- The browser tools in a scheduled run are mcp__claude-in-chrome__* (load them with ToolSearch; if only
  enable__mcp__claude-in-chrome exists, call it first). They work whenever Chrome is open on the Mac with the extension
  signed in to Charlie's account; a window resize dropped the connection once, so leave the window size alone.

## Jobs

### done: Saved logins for the submissions (22 October)
Charlie exported both cookie files and pasted WHOP_COOKIES and VYRO_COOKIES (22 October 19:37 UK). Both sites are signed in as
the studio. When a login expires (a GitHub issue says so), the same three steps again: extension, Export, paste.
Install the Chrome extension "Get cookies.txt LOCALLY" if missing (https://chromewebstore.google.com/search/get%20cookies.txt%20locally).
On https://contentrewards.com/ signed in as the studio account, export the cookies (extension icon, Export, current site),
read the downloaded file and add its text as the GitHub secret WHOP_COOKIES at
https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new. The same for
https://app.vyro.com/campaigns into VYRO_COOKIES. If a site asks to sign in, ask Charlie to sign in, then continue.

### done: Prove the automatic submissions (22 October)
Content Rewards: automatic from GitHub at 18:01 UK (the real dialog read in Chrome, submit.py rewritten to it, the consent
box, a Failed icon beside a refused check, the 30-minute window, a 2 to 5 minute gap before each submission); the sign-in
lives encrypted in tokens/login_whop.enc (logins.yml). Vyro: drops a session that arrives from GitHub's servers, so its
clips go public at 19:00 UK and this run submits them (standing job below). The 21 October links were past Content
Rewards' window and are marked so. First real automatic batch: 23 October 18:01 UK; read status/clips_log.txt after it.

### open: Join the campaigns the scout ranks (22 October)
The scout has not run yet (its runs were held with the rest; the 09:35 UK run tomorrow is the next). Done by hand on 22
October: Vyro's open list read; joined Kevin Langue (4 Imposters vs 1 Real Ghost Hunter, $2.00, Shorts allowed, footage on
Frame.io) and added it; skipped Don't Lie To Me (dating and divorce talk), Ground Stop ("edgy, zero filters"), both Ketone-IQ
(a supplement). Content Rewards: the $10,000 Kai Cenat pool (Reach) sources from his Twitch and YouTube streams (no
provided files, 350K views to qualify, raw stream language) and the MW4 Campaign Moments one is TikTok and Instagram only,
so neither joined. Streamer Discords (N3on, Jynxzi, Clix) not started: needs a studio Discord account.
Set requests/clips.txt to "scout", commit and push, wait for the run, read status/scout.md. Join every campaign marked yes
on Content Rewards (Join or Apply on its page) and the fitting ones at https://app.vyro.com/campaigns (clipping not UGC,
YouTube Shorts allowed, footage provided, family friendly, open). For each joined campaign read its rules page and add an
entry to clips/campaigns.json in the shape of the existing entries (subject, platform, pay_per_1k, min_views, max_payout,
ends, source with the footage link and kind, rules with focus, on_screen, hashtags, description, avoid, min_s, max_s);
commit and push. Also join the clipper programmes of N3on, Kai Cenat, Jynxzi and Clix (their Discords; search "<name>
clipping program" when the link is unknown), get each one's submission link and rules, and add those that allow YouTube
Shorts; skip anything political, adult or not family friendly. List for Charlie anything that needs an application
message or a screen recording.

### open: Instagram and Facebook for Quickplay Clips (22 October)
Charlie asked 22 October 19:45 UK to create the account and the Page; the secrets are his to paste too.
Ask Charlie to create the Instagram account quickplayclips (Creator type) and the Facebook Page "Quickplay Clips" with
the studio email and to link the Instagram account to the Page; wait for his reply. Then in
https://developers.facebook.com/tools/explorer/ (the Meta app the main channel uses) make a long-lived Page access token
for the Page, read its Page ID and the Instagram Business account ID, and add the secrets IG_CLIPS_TOKEN,
IG_CLIPS_USER_ID, FB_CLIPS_PAGE_TOKEN and FB_CLIPS_PAGE_ID. Connect the Instagram account on
https://contentrewards.com/c/settings and https://app.vyro.com/settings.

### open: Two more YouTube channels for the niches (22 October)
Created and signed in by Charlie 22 October 19:45 UK (tokens/youtube_gaming.enc, tokens/youtube_irl.enc; Google blocks
Claude's clicks on its sign-in pages, so the Allow is always his). Both unverified: his number already verified Daily and
Clips (a number verifies 2 channels a year). Left: connect both as accounts on Content Rewards (Settings, Connected
accounts, Connect account, YouTube, a Google window) and Vyro (settings, social account); asked 20:05 UK.
Charlie creates them himself under the studio Google account (https://www.youtube.com/channel_switcher, Create a channel):
"Quickplay Gaming Clips" (the word Gaming in the title) and "Quickplay IRL Clips" (the word IRL in the title); then
https://www.youtube.com/features on each for the phone verification. Ask him for that, wait. Then for each new channel:
open the sign-in link in status/youtube_connect_clips.json (connect_url) while using that channel, copy the code from
the address bar, run the social workflow (https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/social.yml,
Run workflow) with the code and the channel name (gaming or irl); check tokens/youtube_gaming.enc and
tokens/youtube_irl.enc appear. Connect both channels as accounts on https://contentrewards.com/c/settings and
https://app.vyro.com/settings (one Content Rewards account and one Vyro account hold every channel: never a second clipper
account, the platforms ban linked accounts). The campaigns already list their channels in clips/campaigns.json
("channels"); the next 13:00 UK run fills each channel with different moments of the same footage.

### blocked: Two more free model keys (22 October)
Both need an account and a key pasted, so both are Charlie's (asked 22 October 19:45 UK, links given).
With the studio account make free API keys at https://cloud.cerebras.ai/ and https://console.mistral.ai/api-keys and add
the secrets CEREBRAS_API_KEY and MISTRAL_API_KEY.

## Standing jobs (every run)
- Vyro submissions (every run, right after the identity guard; the day's clips go public at 19:00 UK and Vyro drops any session
  that arrives from GitHub's servers, so this is the only route): for every row of clips/submit.csv whose campaign is on
  Vyro, whose public_at_uk has passed within the last 3 days and whose submitted column is empty or starts with "failed":
  on https://app.vyro.com/campaigns/add-clips find the campaign's card (the "card" text in clips/campaigns.json), press
  its Submit post, then "Use a link instead", paste the row's video link, make sure the social account is the row's
  channel (quickplayclips-x9b for clips, the gaming or irl handle otherwise), tick "My post follows campaign rules",
  Continue, and on "Review your post" press Submit post. "Post not submitted: You have already submitted this post"
  counts as done. Write the UK time (or the time plus " (already)") into the row's submitted column; a refusal goes in
  as "failed: <reason>". Stop for the day when the dialog says the account can submit 0 posts today (5 per connected
  account a day). Commit as "Quickplay Studio" and push. Leave a random 2 to 5 minutes between submissions.
  Order (24 October): newest public_at_uk first, so each account's 5 places go to the day's fresh clips (they carry our
  spoken take); older rows only fill places left over. With 5 places per account a day, a row older than a day is
  rarely worth a place: skip rows over 48 hours old when today's rows for that account fill its 5.
- Content Rewards fallback (every run): a Content Rewards row of clips/submit.csv public today whose submitted column
  says "failed: login expired" or "failed: no saved sign-in" is submitted the same way in Chrome (the campaign page's
  Submit clip, paste the link, tick the requirements box, Submit clip) while it is still within 30 minutes of going
  public; then the saved login is re-exported: extension, Export on https://contentrewards.com/c/campaigns, Charlie
  pastes WHOP_COOKIES, Run workflow on https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/logins.yml
  (the paste is his; ask in one line).
- First, the identity guard (Charlie, 22 October: nothing outside the studio Google account, ever): open
  https://myaccount.google.com/ in the run's own tab and read the account shown. It must be studiosocialmedia123@gmail.com;
  any other account (or none) means the wrong Chrome profile: stop every browser step, touch nothing, and tell Charlie in
  one line which account Chrome is signed in as. On each site the signed-in name must be the studio's (Content Rewards
  "Studio SocialMedia", Vyro the studio avatar, GitHub quickplay-studio); a different name on any site stops the run the
  same way. If the GitHub issue "🔒 Security: a sign-in outside the studio account" is open, send Charlie its text first.
- If a GitHub issue titled "Clips: the Content Rewards login has expired" or "... the Vyro login has expired" is open,
  export that site's cookies again into its secret and close the issue.
- Capacity (Charlie, 22 October: fully automatic, never fewer campaigns than the channels can fill): count the active
  campaigns in clips/campaigns.json that still have footage and more than 3 days before "ends". If fewer than
  campaigns.json min_active (6), join enough to reach it, best first: the yes rows of status/scout.md (GitHub refreshes it
  every morning at 09:35 UK; if it is older than 2 days, push "scout" in requests/clips.txt first and wait for the run),
  then Vyro's open list at https://app.vyro.com/campaigns (open each card: clipping, YouTube Shorts allowed, footage
  provided, family friendly, not locked, budget mostly unspent). For each one joined, read its rules and footage link
  (visible once joined) and add the entry to clips/campaigns.json in the shape of the existing ones (channels: gaming for
  game footage, irl for creators and challenges, always clips); commit and push. Skip anything political, adult, gambling,
  supplements or health claims, "edgy" or "unfiltered" shows, and anything without provided footage. GitHub switches a
  campaign off itself when it ends or its budget runs out, and shares the day's clips among the rest.
  Prefer low minimums (Charlie, 22 October: a clip under the minimum earns nothing; the planner already weighs how often
  our clips reach each minimum): status/scout.md now shows YouTube's minimum views read from the page. After joining,
  open the brief (the campaign's Google Doc or reference file) and add the campaign only when ALL hold: it supplies
  footage or names exact videos to clip; it does not ask for original commentary, drama or "bold claims" (Pet Simulator
  99, 22 October); it needs no proof per clip (a support ticket, analytics screenshots or screen recordings: CLASH x HOH,
  22 October); YouTube's budget share is not spent (YoungLA, 22 October); any audience-country rule ("40% from US, UK,
  CA, AU") goes into the entry's rules so the planner can weigh it. Otherwise leave it joined but unused and note why in
  the log.
- status/streamers.md lists the viral streamers right now and "Programmes to join next": for each one, find the official
  clipping programme (Content Rewards, Vyro, the streamer's Discord), join it if YouTube Shorts counts and the footage is
  family friendly, and add it to clips/campaigns.json; note in clips/streamers.json "programme" what you found.
- A new YouTube channel for a niche (Charlie creates it under the studio Google account): sign it in with the social
  workflow's connect link (status/youtube_connect.json, channel name e.g. "gaming"), set "channel": "<name>" on its
  campaigns in clips/campaigns.json, and when he has made its Instagram and Facebook Page add the secrets
  IG_<NAME>_TOKEN, IG_<NAME>_USER_ID, FB_<NAME>_PAGE_TOKEN, FB_<NAME>_PAGE_ID (upper case name).
- Footage (every run): a campaign whose last run says its footage could not be downloaded (status/clips_log.txt: "no
  footage", "download failed", "frameio" or "gdrive" errors) gets its footage link re-read on the campaign page (joined
  campaigns show it) and clips/campaigns.json "source" updated; if the footage is gone for good, set "active": false
  with "why_off".
- Finish by appending one dated line per job to the end of this file's log below, committing and pushing.

- Link the week's Shorts to the long video (Mondays only, after the other standing jobs; 23 October, from Charlie's
  upload checklist: Shorts that link to a long video feed it watch hours, the second Partner Programme route, 8,000
  hours a year from February 2027): in YouTube Studio for Quickplay Daily (the studio account's channel only), take the
  newest public weekly long video (status/weekly*.json or the channel's Videos tab) and, for the 10 Shorts of the last 7
  days with the most views (analytics/shorts.csv yt_views), open each Short's Details, set "Related video" to that long
  video and Save. Then on the long video itself add an end screen (Editor, End screen, the "Best for viewer" video and a
  Subscribe element) if it has none. Log one line: how many Shorts were linked. Skip quietly when there is no weekly
  video yet.
- Watchlist campaigns (every run while status/watch.json shows an item in build-up, surging or launch; 23 October: GTA 6,
  out 19 November 2026): search Vyro's and Content Rewards' campaign lists for the item's terms (GTA 6, GTA VI,
  Grand Theft Auto VI) and for streamers playing it, and join any campaign that pays for YouTube, Instagram or TikTok
  views and whose rules the channel can keep (family friendly: no violence or crime moments in the clips). Add each to
  clips/campaigns.json as the "Join the campaigns" job says. Log what was found, even when nothing was.
## Log
- 22 October 19:45 UK: first Mac run. Chrome's connection dropped after a window resize; the cookie export, every secret and every account
  are Charlie's hands (see Who does what), so one message asked him for all of them with links. Nothing on GitHub can submit or scout until
  WHOP_COOKIES and VYRO_COOKIES exist.
- 22 October 20:10 UK: cookies in; submit.py rewritten to the real forms; GitHub's malicious-workflow hold found and fixed (named secrets);
  gaming and irl channels signed in; Kevin Langue joined on Vyro; three Vyro and two Content Rewards campaigns judged and skipped.
- 22 October 20:40 UK: identity guard added (pipeline/identity.py, audit.yml every 6 hours, a gate step in every posting workflow, the
  Chrome-profile check above); the campaign-site sign-ins moved out of the clips workflow into tokens/ (logins.yml) after GitHub held
  every clips run that read the cookie secrets.
- 22 October 21:00 UK: Vyro rejects the saved session on GitHub (the vyro_sid cookie is dropped on arrival); Content Rewards works. Vyro
  submissions are now a standing job of this run (above) with Vyro clips public at 19:00 UK; GitHub leaves Vyro rows alone. Three
  Content Rewards rows of 21 October had been marked "already" by mistake (the dialog's standing label); corrected, the reading fixed.
- 22 October 21:30 UK: the daily task is on (19:07 UK, Vyro submissions first). Vyro signed the Chrome profile out when GitHub presented
  the saved session (hijack protection): Charlie signs back in with Google; nothing on GitHub reads tokens/login_vyro.enc any more.
  developers.facebook.com is logged out in the studio profile; the Instagram token and the Cerebras and Mistral keys are his, links sent.
- 22 October 23:55 UK: "do 1": the planner now weighs each campaign by how often our clips reach its minimum views; the scout reads YouTube's rate,
  minimum and budget from the page. Joined Pet Simulator 99 and CLASH x HOH to check them: neither is usable (original drama content with no
  footage; a support ticket with analytics per clip), so neither was added. Skipped YoungLA (YouTube budget spent) and Stranger Than Heaven (crime theme).
