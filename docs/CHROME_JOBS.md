# Chrome jobs: what the Mac session does in Charlie's browser

The cloud sessions and GitHub cannot click in Charlie's Chrome. The scheduled task "Quickplay: Chrome jobs (on the Mac)"
runs on his Mac with Claude in Chrome (daily at 19:07 UK, and whenever a cloud session fires it with new work). It reads
this file, does every job marked **open** in order, asks Charlie only for passwords, codes and accounts he must create
himself, then marks each job **done** (with the date and a line on what happened) or **blocked** (why, and what Charlie
must do), commits as "Quickplay Studio" and pushes. Rules: CLAUDE.md (studio account only, never type passwords, keys
only in GitHub secrets, family friendly, UK English, no em or en dashes). New jobs go at the top of the list, newest
first; the task text of a fired run counts as an extra job.

## Jobs

### open: Saved logins for the submissions (22 October)
Install the Chrome extension "Get cookies.txt LOCALLY" if missing (https://chromewebstore.google.com/search/get%20cookies.txt%20locally).
On https://contentrewards.com/ signed in as the studio account, export the cookies (extension icon, Export, current site),
read the downloaded file and add its text as the GitHub secret WHOP_COOKIES at
https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new. The same for
https://app.vyro.com/campaigns into VYRO_COOKIES. If a site asks to sign in, ask Charlie to sign in, then continue.

### open: Prove the automatic submissions (22 October)
Set requests/clips.txt to "submit probe", commit and push, wait for the clips workflow run, read status/clips_log.txt and
status/submit_*.png. If a site's form differs from what pipeline/submit.py expects (submit_cr and submit_vyro: the Submit
clip or Submit post button, the platform choice, the link box, the confirm button, the answer text), fix those steps,
run python tests/test_submit.py, commit and push, then set requests/clips.txt to "submit" and repeat until the run reports
every due row of clips/submit.csv submitted.

### open: Join the campaigns the scout ranks (22 October)
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
Ask Charlie to create the Instagram account quickplayclips (Creator type) and the Facebook Page "Quickplay Clips" with
the studio email and to link the Instagram account to the Page; wait for his reply. Then in
https://developers.facebook.com/tools/explorer/ (the Meta app the main channel uses) make a long-lived Page access token
for the Page, read its Page ID and the Instagram Business account ID, and add the secrets IG_CLIPS_TOKEN,
IG_CLIPS_USER_ID, FB_CLIPS_PAGE_TOKEN and FB_CLIPS_PAGE_ID. Connect the Instagram account on
https://contentrewards.com/c/settings and https://app.vyro.com/settings.

### open: Two more free model keys (22 October)
With the studio account make free API keys at https://cloud.cerebras.ai/ and https://console.mistral.ai/api-keys and add
the secrets CEREBRAS_API_KEY and MISTRAL_API_KEY.

## Standing jobs (every run)
- If a GitHub issue titled "Clips: the Content Rewards login has expired" or "... the Vyro login has expired" is open,
  export that site's cookies again into its secret and close the issue.
- If status/scout.md is older than 7 days, run "scout" again and join the new yes rows as above.
- Finish by appending one dated line per job to the end of this file's log below, committing and pushing.

## Log
