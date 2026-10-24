# Chrome run: one-off jobs, history and log

The Mac's card is docs/CHROME_JOBS.md, and its occasional jobs are in docs/CHROME_OCCASIONAL.md. This file holds three things:
- the one-off jobs, newest first, marked open, waiting (on Charlie), blocked or done;
- how the work is split between Charlie and Claude;
- the log, which is append-only.

`python3 pipeline/mac_rows.py` lists only the "### open:" jobs, so a job waiting on Charlie costs the Mac nothing until a session marks it open again.

## Who does what (learnt 22 October)
Claude in Chrome acts inside web pages only, and Claude never handles credentials. So in every job:
- **Charlie's hands:**
  - clicking an extension's toolbar icon or popup (the cookie export);
  - pasting any secret, key, token or cookie text into GitHub (https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new);
  - typing a password or code;
  - creating an account (YouTube channels, Instagram, Facebook, Mistral, SambaNova);
  - clicking Allow on an OAuth or Connect screen.

  The run opens the page for him, asks in one message with the exact steps and links, and waits.
- **Claude's hands:** everything else on a page (joining campaigns, reading rules, forms without credentials), pushing requests (requests/clips.txt), reading the run results, fixing pipeline/submit.py, editing clips/campaigns.json, the social workflow runs, and these files.
- **The browser tools** in a scheduled run are mcp__claude-in-chrome__*. Load them with ToolSearch; if only enable__mcp__claude-in-chrome exists, call it first. They work whenever Chrome is open on the Mac with the extension signed in. A window resize dropped the connection once, so leave the window size alone.

## One-off jobs

### waiting: Instagram and Facebook for Quickplay Clips (22 October)
Charlie asked on 22 October at 19:45 UK to create the account and the Page; the secrets are his to paste too.
Waiting for him:
- the Instagram account quickplayclips (Creator type);
- the Facebook Page "Quickplay Clips", made with the studio email;
- the Instagram account linked to the Page.

Then, in https://developers.facebook.com/tools/explorer/ (the Meta app the main channel uses):
1. Make a long-lived Page access token for the Page.
2. Read its Page ID and the Instagram Business account ID.
3. Charlie pastes the secrets IG_CLIPS_TOKEN, IG_CLIPS_USER_ID, FB_CLIPS_PAGE_TOKEN and FB_CLIPS_PAGE_ID.
4. Connect the Instagram account on https://contentrewards.com/c/settings and https://app.vyro.com/settings.

From 24 October the identity audit refreshes an IG_<CHANNEL>_TOKEN by itself every week (tokens/instagram_<channel>.enc), so a pasted key only needs pasting once.

### waiting: Two more YouTube channels for the niches (22 October)
Charlie created and signed in both on 22 October at 19:45 UK (tokens/youtube_gaming.enc, tokens/youtube_irl.enc). Google blocks Claude's clicks on its sign-in pages, so the Allow is always his. Both channels are unverified: his number already verified Daily and Clips, and a number verifies 2 channels a year.

What is left is to connect both as accounts:
- on Content Rewards: Settings, Connected accounts, Connect account, YouTube, then a Google window;
- on Vyro: settings, social account.

Asked at 20:05 UK. Use one Content Rewards account and one Vyro account for every channel: never a second clipper account, because the platforms ban linked accounts.

### waiting: More free model keys (22 October; corrected 24 October)
Each needs an account and a key pasted, so each is Charlie's. He was asked on 22 October at 19:45 UK, with links. With the studio account he makes free API keys:
- at https://console.mistral.ai/api-keys (free plan: a verified phone number, no card);
- at https://cloud.sambanova.ai (no payment method, or the free tier ends).

Then he adds the secrets MISTRAL_API_KEY and SAMBANOVA_API_KEY. Not Cerebras: its trial credit needs a payment method.

### done: Join the campaigns the scout ranks (22 October; became the Capacity job on 24 October)
Done by hand on 22 October:
- **Vyro:** read the open list. Joined Kevin Langue (4 Imposters vs 1 Real Ghost Hunter, $2.00, Shorts allowed, footage on Frame.io) and added it. Skipped Don't Lie To Me (dating and divorce talk), Ground Stop ("edgy, zero filters") and both Ketone-IQ campaigns (a supplement).
- **Content Rewards:** neither campaign was joined.
  - The $10,000 Kai Cenat pool (Reach) sources from his Twitch and YouTube streams: no provided files, 350K views to qualify, and raw stream language.
  - The MW4 Campaign Moments campaign is TikTok and Instagram only.
- **Streamer Discords** (N3on, Jynxzi, Clix): not started, because they need a studio Discord account.

What remains runs as the occasional Capacity and Streamer programmes jobs (docs/CHROME_OCCASIONAL.md).

### done: Prove the automatic submissions (22 October)
- **Content Rewards:** automatic from GitHub. The real dialog was read in Chrome and submit.py rewritten to it: the consent box, a Failed icon beside a refused check, the 30-minute window, and a 2 to 5 minute gap before each submission. The sign-in lives encrypted in tokens/login_whop.enc (logins.yml).
- **Vyro:** drops a session that arrives from GitHub's servers, so its clips go public at 19:00 UK and the Mac run submits them.

### done: Saved logins for the submissions (22 October)
Charlie exported both cookie files and pasted WHOP_COOKIES and VYRO_COOKIES at 19:37 UK. When a login expires (a GitHub issue says so), he repeats the same three steps:
1. The Chrome extension "Get cookies.txt LOCALLY" (https://chromewebstore.google.com/search/get%20cookies.txt%20locally).
2. Export on the site, signed in as the studio.
3. Paste as the secret.

## Log
- 22 October 19:45 UK: first Mac run.
  - Chrome's connection dropped after a window resize.
  - The cookie export, every secret and every account are Charlie's hands, so one message asked him for all of them with links.
  - Nothing on GitHub can submit or scout until WHOP_COOKIES and VYRO_COOKIES exist.
- 22 October 20:10 UK:
  - Cookies in, and submit.py rewritten to the real forms.
  - GitHub's malicious-workflow hold found and fixed (named secrets).
  - Gaming and irl channels signed in; Kevin Langue joined on Vyro.
  - Three Vyro and two Content Rewards campaigns judged and skipped.
- 22 October 20:40 UK:
  - Identity guard added: pipeline/identity.py, audit.yml every 6 hours, a gate step in the posting workflows, and the Chrome profile check.
  - The campaign-site sign-ins moved out of the clips workflow into tokens/ (logins.yml), after GitHub held every clips run that read the cookie secrets.
- 22 October 21:00 UK:
  - Vyro rejects the saved session on GitHub (the vyro_sid cookie is dropped on arrival); Content Rewards works.
  - Vyro submissions are now a standing job of the Mac run, with Vyro clips public at 19:00 UK.
  - Three Content Rewards rows of 21 October had been marked "already" by mistake (the dialog's standing label); corrected, and the reading fixed.
- 22 October 21:30 UK:
  - The daily task is on (19:07 UK).
  - Vyro signed the Chrome profile out when GitHub presented the saved session (hijack protection), so Charlie signs back in with Google.
  - developers.facebook.com is logged out in the studio profile.
- 22 October 23:55 UK:
  - The planner weighs each campaign by how often our clips reach its minimum views.
  - Pet Simulator 99 and CLASH x HOH joined to check them; neither is usable (original drama content with no footage; a support ticket with analytics per clip).
  - Skipped YoungLA (YouTube budget spent) and Stranger Than Heaven (crime theme).
- 24 October 17:00 UK: the card was cut from 18.5 KB to under 4 KB (docs/CHROME_JOBS.md).
  - `python3 pipeline/mac_rows.py` now hands the run its Vyro rows (newest first, the places left per account, never an expired row), any Content Rewards rescue, the occasional jobs due and the open one-off jobs. It says "NOTHING TO DO" when there is nothing, so a late pass stops at once.
  - `mac_rows.py done` marks a row without opening clips/submit.csv.
  - Jobs that wait on Charlie are marked waiting, so the run no longer re-asks him every evening.
