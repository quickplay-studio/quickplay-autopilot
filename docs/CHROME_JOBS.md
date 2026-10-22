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

### blocked: Saved logins for the submissions (22 October)
Waiting for Charlie (asked 22 October 19:45 UK): install the extension, Export on contentrewards.com and app.vyro.com,
paste the two files as WHOP_COOKIES and VYRO_COOKIES. Content Rewards is signed in as Studio SocialMedia; Vyro unchecked.
Install the Chrome extension "Get cookies.txt LOCALLY" if missing (https://chromewebstore.google.com/search/get%20cookies.txt%20locally).
On https://contentrewards.com/ signed in as the studio account, export the cookies (extension icon, Export, current site),
read the downloaded file and add its text as the GitHub secret WHOP_COOKIES at
https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new. The same for
https://app.vyro.com/campaigns into VYRO_COOKIES. If a site asks to sign in, ask Charlie to sign in, then continue.

### open: Prove the automatic submissions (22 October)
After the saved logins exist. The 22 October 18:01 UK batch: 0 of 23 submitted, no cookies.
Set requests/clips.txt to "submit probe", commit and push, wait for the clips workflow run, read status/clips_log.txt and
status/submit_*.png. If a site's form differs from what pipeline/submit.py expects (submit_cr and submit_vyro: the Submit
clip or Submit post button, the platform choice, the link box, the confirm button, the answer text), fix those steps,
run python tests/test_submit.py, commit and push, then set requests/clips.txt to "submit" and repeat until the run reports
every due row of clips/submit.csv submitted.

### open: Join the campaigns the scout ranks (22 October)
After the saved logins exist (the scout needs the Content Rewards cookies; status/scout.md does not exist yet).
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
Charlie asked 22 October 19:45 UK to create them. The run opens the connect_url for each; Charlie clicks Allow.
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
- If a GitHub issue titled "Clips: the Content Rewards login has expired" or "... the Vyro login has expired" is open,
  export that site's cookies again into its secret and close the issue.
- status/scout.md is refreshed by GitHub every morning (09:35 UK): join any new yes row as above, and add it to
  clips/campaigns.json. If the file is older than 2 days, run "scout" yourself first.
- status/streamers.md lists the viral streamers right now and "Programmes to join next": for each one, find the official
  clipping programme (Content Rewards, Vyro, the streamer's Discord), join it if YouTube Shorts counts and the footage is
  family friendly, and add it to clips/campaigns.json; note in clips/streamers.json "programme" what you found.
- A new YouTube channel for a niche (Charlie creates it under the studio Google account): sign it in with the social
  workflow's connect link (status/youtube_connect.json, channel name e.g. "gaming"), set "channel": "<name>" on its
  campaigns in clips/campaigns.json, and when he has made its Instagram and Facebook Page add the secrets
  IG_<NAME>_TOKEN, IG_<NAME>_USER_ID, FB_<NAME>_PAGE_TOKEN, FB_<NAME>_PAGE_ID (upper case name).
- Finish by appending one dated line per job to the end of this file's log below, committing and pushing.

## Log
- 22 October 19:45 UK: first Mac run. Chrome's connection dropped after a window resize; the cookie export, every secret and every account
  are Charlie's hands (see Who does what), so one message asked him for all of them with links. Nothing on GitHub can submit or scout until
  WHOP_COOKIES and VYRO_COOKIES exist.
