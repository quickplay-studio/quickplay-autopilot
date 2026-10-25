# Mac card: the Chrome run (19:07 UK, and whenever a cloud session fires it)

Read this card, then run `python3 pipeline/mac_rows.py`. Read nothing else unless its answer names a file.
- Account: the studio Google account only.
- Credentials: never type, paste or read out a password, code, key or cookie. Those are Charlie's hands: ask him in one message with the steps and links, then wait.
- Style: family friendly, UK English, no em or en dashes.
- Browser tools: mcp__claude-in-chrome__* (load them with ToolSearch). Leave the window size alone.

1. Run `git pull --rebase`.
2. Check the identity first. Open https://myaccount.google.com/ in the run's own tab: it must show
   studiosocialmedia123@gmail.com. Any other account, or none: stop every browser step, touch nothing, and tell Charlie
   in one line which account Chrome shows. On each site the signed-in name must be the studio's: Content Rewards
   "Studio SocialMedia", Vyro the studio avatar, GitHub quickplay-studio. Another name stops the run the same way.
3. Run `python3 pipeline/mac_rows.py`.
   - "NOTHING TO DO": stop here, with no commit.
   - The security issue: send Charlie its text and stop.
   - A site login has expired: ask Charlie to export that site's cookies again and paste them. The steps: the extension
     "Get cookies.txt LOCALLY", Export on the site, paste as WHOP_COOKIES or VYRO_COOKIES at
     https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions, then Run workflow on
     https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/logins.yml.
   - If the script fails, say so in one line and stop. GitHub keeps the rows open for 30 hours.
4. Submit the Vyro rows in the order listed. The script already keeps to 5 a day per account, newest first, and to the
   rows GitHub left open: a row over 30 hours old is listed only when its views justify a late submission. For each row:
   1. Open https://app.vyro.com/campaigns/add-clips and find the card the row names.
   2. Press Submit post, then "Use a link instead", and paste the row's link.
   3. Make sure the social account is the row's channel, and tick "My post follows campaign rules".
   4. Press Continue, then Submit post on "Review your post".
   5. Mark it: `python3 pipeline/mac_rows.py done <clip> now`.
      - "Post not submitted: You have already submitted this post": `... done <clip> now (already)`.
      - A refusal: `... done <clip> failed: <reason>`.

   Wait a random 2 to 5 minutes between submissions. When the dialog says the account has 0 posts left today, stop that account.
5. Content Rewards rescue rows: GitHub's sign-in failed and the clip is still inside its 30 minutes. Open the campaign
   page, press Submit clip, paste the link, tick the requirements box and press Submit clip. Mark it as in step 4, then
   ask Charlie for the cookie export (step 3).
6. Community poll listed (status/community.json is dated today and not yet posted): in YouTube Studio, as the studio
   account, on Quickplay Daily's Community tab, post the text line, then the poll with the options shown, then run
   `python3 pipeline/community.py posted`. No Community tab offered: `python3 pipeline/community.py unavailable`.
7. Occasional jobs listed: their steps are in docs/CHROME_OCCASIONAL.md. One-off jobs listed: their steps are in
   docs/CHROME_LOG.md. Read only the section the job names.
8. Finish: add one dated line at the end of docs/CHROME_LOG.md (submitted, refused, blocked). Commit as "Quickplay Studio"
   <quickplay-studio@users.noreply.github.com>, run `git pull --rebase`, and push.

A cloud session that needs the browser adds a one-off job ("### open: ...") at the top of docs/CHROME_LOG.md's jobs, or
fires the task with the job text. It never uses a browser itself. History, earlier jobs and the log: docs/CHROME_LOG.md.
