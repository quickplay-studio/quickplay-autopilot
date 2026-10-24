# TikTok: the plan (24 October 2026)

Free, rule-safe and led by data. Full research with sources: the 24 October report (TikTok's developer guidelines of
4 August 2026, Creator Rewards, AI labels), summarised here.

## Where we stand
- TikTok blocked every post as spam on 19 October (`config.json` `tiktok_mode` "off" since). No error code was saved, so
  the cause is unknown.
- **No automatic public posting, ever.** Before TikTok audits an app, it may only post "only me" (SELF_ONLY), and the
  audit is closed to "a utility tool to help upload contents to the account(s) you or your team manages". Don't apply
  for the Direct Post audit.
- **The safe route is semi-manual.** GitHub renders the video and writes the caption, and the draft lands in the TikTok
  app (inbox). Charlie posts it there (or schedules it in TikTok Studio). Our numbers come back automatically.
- **Money:** Creator Rewards pays only for original videos over 1 minute, and needs 10k followers plus 100k views in
  30 days. Creators report $0.40 to $1.00 per 1,000 qualified views. Clip campaigns that list TikTok pay about $0.50 to
  $3 per 1,000.

## What the code does now (social.py)
- `tiktok_mode` stays "off" until Phase 0 is done.
- Inbox drafts: at most `tiktok_per_day` (2) in 24 hours, never over TikTok's 5 pending. An upload counts as sent only
  once TikTok confirms it landed (`tiktok_pending`, then `tiktok`; asked again each run, failed after 24 hours).
- Direct mode never chooses public. It uses `tiktok_privacy` when Charlie sets it and the account offers it, otherwise
  SELF_ONLY. Branded-content toggles go off, the AI label goes on, and a video longer than the account's maximum is
  refused.
- If TikTok answers `spam_risk_user_banned_from_posting` or `spam_risk_too_many_posts`, the code:
  - writes `status/tiktok_safety.json`;
  - opens the issue "⛔ TikTok stopped posting";
  - stops TikTok until that file is deleted.
- New sign-ins ask only for `user.info.basic, user.info.stats, video.list, video.upload` (no `video.publish`).
- `python pipeline/social.py tiktok-stats` runs every social run and is read-only. It writes each public post's views,
  likes, comments and shares to `analytics/tiktok.csv`, matched to its Short where it can be, and followers to
  `status/tiktok_account.json`. Posts set to "only me" never show up there.

## Phase 0, now: Charlie, about 10 minutes
1. In the TikTok app, go to Settings and privacy, then Account, then Account status. Note any violation, restriction and
   its date.
2. In TikTok Studio, check for posts marked "not eligible for For You".
3. At https://developers.tiktok.com/, note whether the app is live or in sandbox, and which scopes it has.
4. Tell Claude the account's handle so it goes on the identity allowlist (`config.json` `accounts.tiktok` is empty;
   until then the Quickplay name rule checks the display name).

If posting is restricted, wait it out. Never open a new account to get round it.

## Phase 1, weeks 1 and 2: data before posts
Connect with the trimmed scopes, let `tiktok-stats` fill `analytics/tiktok.csv`, and backfill any posts already
public. No posting.

## Phase 2, 28 days: the test (needs Charlie's yes)
- **Daily line:** 2 drafts a day for 14 days, then 3.
  - Use the day's top picks, each also a YouTube Short and an Instagram Reel, so every comparison is paired.
  - Charlie ticks the AI-generated label on every post.
  - One post a day is a 61 to 75 second cut, to test Creator Rewards.
  - Space posts at least 3 hours apart.
- **Clips line:** only campaigns that list TikTok, 1 or 2 a day. A new clips account needs Charlie.

## Metrics
- **Per post:** TikTok views at 48 hours and 7 days, against the same Short's YouTube and Instagram views; like,
  comment and share rates.
- **Per account:** followers gained a week, views in 30 days (Creator Rewards needs 100k), and days to 10k followers
  (10,000 minus followers, divided by the 28-day average daily gain).

## Stop and scale rules
- **Safety stop:** stop TikTok and review if any of these happens:
  - a strike or a posting restriction;
  - any `spam_risk` answer (automatic, see above);
  - 2 posts not eligible for For You within 7 days.

  A second time, TikTok stops for good.
- **Platform stop on day 28** (about 70 posts): if the median 7-day views are under 300 and under the same Shorts'
  Instagram median, TikTok Daily stops for good.
- **Scale on day 28:** if the median 7-day views are at or above the same Shorts' YouTube median (or over 1,000), with
  no safety flags, go to 5 a day.
- **10k rule:**
  - Over 365 days to 10k: post for reach only, no long cuts for money.
  - Under 180 days: the long cut becomes the default for picks.
- **Clips stop:** after 20 TikTok clips for a campaign with none past its minimum, stop TikTok for that campaign.

## What Charlie does by hand
- Phase 0 (above) and the yes for Phase 2.
- **Each post:** paste the caption from the status file, set privacy, tick AI-generated, then post or schedule in
  TikTok Studio. About a minute.
- Keep the account personal: Creator Rewards excludes business accounts.
