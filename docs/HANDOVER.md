# Handover to a chat on Charlie's Mac (22 October 2026, 19:30 UK)

Read this first, then CLAUDE.md, then docs/CHROME_JOBS.md. You are picking up from a cloud chat that built everything on
GitHub but has no browser. You run on Charlie's Mac with Claude in Chrome, so you can sign in to sites, join campaigns and
add GitHub secrets. Charlie's standing instruction: "use Claude on Chrome to do everything you need to do and then ask me
to do passwords etc; I would like minimal input, only with things you cannot progress." Ask him only for passwords, codes
and the accounts he must create himself (YouTube channels, Instagram, Facebook); otherwise carry on, and tell him in one
line when each job is done.

## What this is
Two YouTube lines under the studio Google account (studiosocialmedia123@gmail.com), fully automated by GitHub Actions in
quickplay-studio/quickplay-autopilot:
- Quickplay Daily: 40 original Shorts a day written from trends, every Short a data test, the goal being YouTube Partner
  Program (1,000 subscribers and 10M Shorts views in 90 days before 1 February 2027).
- Quickplay Clips (@QuickplayClips-x9b) and, once signed in, Quickplay Gaming Clips and Quickplay IRL Clips: clips made
  from campaign-permitted footage (Content Rewards and Vyro clipping campaigns, paid per 1,000 views), uploaded,
  commented and submitted to the campaigns by GitHub (pipeline/clips.py, pipeline/submit.py). Each channel gets
  different moments of the same footage, its own daily number and ceiling.
Money so far: see https://quickplay-studio.github.io/quickplay-autopilot/clips.html. The Monday report is a GitHub issue
labelled weekly.

## Rules that never bend (CLAUDE.md has them all)
Studio account only, never Charlie's personal accounts. Never type passwords or create accounts: he does. Keys only in
GitHub secrets (https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new), never in chat.
Family friendly, UK English, no em or en dashes. Only campaign-permitted footage. One Content Rewards account and one
Vyro account hold every channel as connected accounts (a second clipper account is "linked accounts" and gets banned).
Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>, run tests/ before each push, git pull --rebase.

## What GitHub already does (nothing to build, only to connect)
- Clips: 10:00 UK prepare, 13:00 UK make and upload (public together at 18:00 UK), batch runs at 18:01 and 22:01 UK
  that post Reels, comment, and submit every link to its campaign (needs the saved logins WHOP_COOKIES and
  VYRO_COOKIES), 23:30 UK stats, 09:35 UK scout (status/scout.md: campaigns ranked by money and heat; status/streamers.md:
  the viral streamers and programmes to join next).
- Campaign selection and the clip planner follow live YouTube searches and trend heat; hooks and titles are brand-safe
  filtered; layouts, captions, length and titles are tested on every clip.

## The jobs, in order (docs/CHROME_JOBS.md has the detail; do them there and mark them)
1. Saved logins: export cookies for contentrewards.com and app.vyro.com with the "Get cookies.txt LOCALLY" extension
   into the secrets WHOP_COOKIES and VYRO_COOKIES.
2. Prove submissions: "submit probe" in requests/clips.txt, read status/clips_log.txt and status/submit_*.png, fix
   pipeline/submit.py's clicks (submit_cr, submit_vyro) to each site's real form, test with python tests/test_submit.py,
   then "submit" until every due row of clips/submit.csv is submitted.
3. Campaigns: "scout", then join every yes row on Content Rewards and the fitting Vyro ones; add each to
   clips/campaigns.json (copy an existing entry's shape; set "channels" to ["clips", "gaming"] for game footage or
   ["clips", "irl"] for creators and challenges). Join the N3on, Kai Cenat, Jynxzi and Clix clipper programmes if they
   allow YouTube Shorts and the footage is family friendly.
4. Two more YouTube channels: ask Charlie to create "Quickplay Gaming Clips" and "Quickplay IRL Clips" under the studio
   account (https://www.youtube.com/channel_switcher, then https://www.youtube.com/features to verify). Sign each in:
   open connect_url from status/youtube_connect_clips.json while using that channel, copy the code, run the social
   workflow (https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/social.yml) with the code and the
   channel name gaming or irl; tokens/youtube_gaming.enc and tokens/youtube_irl.enc appear. Connect both channels as
   accounts on https://contentrewards.com/c/settings and https://app.vyro.com/settings.
5. Instagram and Facebook: ask Charlie to create the Instagram account quickplayclips (Creator) and the Facebook Page
   "Quickplay Clips", linked; then in https://developers.facebook.com/tools/explorer/ make a long-lived Page token, read
   the Page ID and Instagram Business ID, add the secrets IG_CLIPS_TOKEN, IG_CLIPS_USER_ID, FB_CLIPS_PAGE_TOKEN,
   FB_CLIPS_PAGE_ID; connect the Instagram account on both campaign platforms.
6. Free model keys: https://console.mistral.ai/api-keys into MISTRAL_API_KEY (free plan, a verified phone, no card) and
   https://cloud.sambanova.ai into SAMBANOVA_API_KEY (no payment method). Not Cerebras: its trial needs a card.
7. When done: append a dated section to docs/CLIPS.md, and schedule the standing jobs of docs/CHROME_JOBS.md as a daily
   task at 19:07 UK that requires this computer (create it from this Mac chat so it is bound to the Mac).

## Where things are
docs/NEXT.md (the build log, newest last), docs/CLIPS.md (the clips line), docs/CHROME_JOBS.md (browser jobs and their
status), status/clips_log.txt (the last clips run), clips/campaigns.json (every campaign and its rules),
clips/streamers.json (the viral streamers watched), analytics/weekly.md (the Monday report).
