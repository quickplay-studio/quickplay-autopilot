# Occasional Mac jobs (run only when `python3 pipeline/mac_rows.py` lists them; the card is docs/CHROME_JOBS.md)

## Capacity
Join campaigns until at least min_active (clips/campaigns.json, 6) are live: active, with footage, more than 3 days before
"ends". Best first: the yes rows of status/scout.md (GitHub refreshes it at 09:35 UK; if it is over 2 days old, push
"scout" in requests/clips.txt and wait for the run), then https://app.vyro.com/campaigns (open each card: clipping, YouTube
Shorts allowed, footage provided, family friendly, not locked, budget mostly unspent). Prefer low minimum views.
Add a campaign only when ALL hold: it supplies footage or names exact videos; it does not ask for original commentary,
drama or "bold claims"; it needs no proof per clip (tickets, analytics screenshots, screen recordings); YouTube's budget
share is not spent. Skip politics, adult, gambling, supplements or health claims, "edgy" or "unfiltered" shows.
For each one joined: read its rules and footage link (visible once joined) and add an entry to clips/campaigns.json in the
shape of the existing ones (subject, platform, pay_per_1k, min_views, max_payout, ends, source, rules with focus,
on_screen, hashtags, description, avoid, min_s, max_s, card, channel: one only, gaming for game footage or irl for creators
and challenges; pipeline/clips.py pins an older "channels" list to its first non-clips channel; any audience-country rule goes into rules). Joined but unusable: note why in the log.

## Daily sound campaigns
Campaigns that pay per 1,000 views for a Short that uses a sound or carries a brand hashtag: no footage, nobody on camera,
paid on Quickplay Daily's own views (status/scout.md, "For Quickplay Daily's own views"; Vyro's open list too). Join with
the studio account: open the link, press Join or Apply, and connect the Quickplay Daily YouTube channel on the site
(Content Rewards: Settings, Connected accounts; Vyro: Settings, Social accounts). Join only when ALL hold: YouTube Shorts
are paid; family friendly (no gambling, crypto, trading, finance, alcohol, adult, politics or health claims); nobody has
to appear on camera; no proof per post beyond the link; no window for the link under a day on Content Rewards (Daily's
links go in once a day). From the brief take the sound file's download link (a direct https link to the file; a Google
Drive or Dropbox share link works, a web page does not), the hashtags and the end date. Add to clips/campaigns.json, with
"daily": true and no "source" or "rules" (the clips line must not make clips for it):
`"<id>": {"daily": true, "active": true, "name": "...", "card": "<as the site lists it>", "platform": "Content Rewards" or
"Vyro", "url": "<campaign page>", "pay_per_1k": 0.0, "min_views": 0, "max_payout": 0, "subject": "...", "hashtags":
["#Brand"], "sound_url": "<the sound file's https link>", "ends": "YYYY-MM-DD", "joined": "<today>"}`.
From the next render 30% of Daily's Shorts (config daily_sponsor_share) carry it: its sound as the music, #ad and the
hashtags first, paid promotion on, a clips/submit.csv row (channel daily). The Vyro rows come to you in step 4 (the account
is Quickplay Daily); GitHub submits Content Rewards. No sound file in the brief: leave "sound_url" out and the Shorts carry
the hashtags only. Log what was joined and why anything was skipped.

## Streamer programmes
For each name listed: find the official clipping programme (Content Rewards, Vyro, the streamer's Discord), join it if
YouTube Shorts counts and the footage is family friendly, add it to clips/campaigns.json, and note what you found in
clips/streamers.json "programme". A Discord needs a studio Discord account: that is Charlie's to create.

## Related video (Mondays)
In YouTube Studio for Quickplay Daily only: take the newest public weekly long video; for the 10 Shorts of the last 7 days
with the most views (`python3 pipeline/mac_rows.py top`),
open each Short's Details, set "Related video" to that long video and Save. On the long video add an end screen (the
"Best for viewer" video and Subscribe) if it has none. Skip quietly when there is no weekly video yet. Log how many.

## Watchlist campaigns
Search Vyro's and Content Rewards' campaign lists for the listed events' terms (status/watch.json "terms") and for
streamers playing them; join any campaign that pays for YouTube, Instagram or TikTok views whose rules the channel can
keep (family friendly: no violence or crime moments), and add it as in Capacity. Log what was found, even nothing.

## Footage
Re-read the listed campaigns' footage links on their campaign pages (joined campaigns show them) and update "source" in
clips/campaigns.json; if the footage is gone for good, set "active": false with "why_off".

## A new YouTube channel for a niche (when Charlie has made one)
Sign it in with the social workflow's connect link (status/youtube_connect.json, channel name such as "gaming"); set
"channel" on its campaigns in clips/campaigns.json; once he has made its Instagram and Facebook Page, the secrets
IG_<NAME>_TOKEN, IG_<NAME>_USER_ID, FB_<NAME>_PAGE_TOKEN and FB_<NAME>_PAGE_ID are his to paste (upper case name).
