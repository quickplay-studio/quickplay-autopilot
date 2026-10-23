# Overnight report, 23 to 24 October 2026

Charlie went to bed at about 22:50 UK and asked for work to continue until his Claude usage ran out, then a full report.
This file is written as the night goes, so it is complete up to the last change even if the session stops mid-task.
Newest work at the bottom of each section. Every change ran the full test suite before it was pushed.

## Changes made tonight (before bed, already reported)

- Writer: strongest free models write first (Groq, OpenRouter, then Gemini Flash); Claude edits titles, hooks and endings
  (capped at 12 a day) and writes 1 board in 4 (capped at 4 a day); usage on the hub.
- Fact packs: misquoted sentences matched to the page, second-opinion facts from a stronger free model, no packs for topics
  already covered, Wikipedia citations removed instead of failing a board.
- Clips: the Instagram and campaign-submission step had never run (a schedule typo); fixed. Clips that an unverified
  channel refuses go up on Quickplay Clips. Moments scored for virality, 25 to 75 seconds, our own spoken take on every
  clip, paid clips labelled #ad.
- 15 better Shorts a day as a judged test (verdict 1 November), category shares from the data, posting in each
  category's best part of the day, new categories on test (Animals, Food, Cars, History), a named-series test for
  subscribers.
- Watching: daily funnel with stuck-stage alerts, silent-job alerts, a daily rule and law watch, a GTA 6 watchlist,
  competitor research, feed share per Short, Instagram views per clip, pounds next to dollars, a live jobs panel and an
  export tab on the hub, a weekly Claude review every Monday.

## Changes made overnight

1. **End-to-end test of tonight's build (23:05 UTC).** A full trends run, then the writer, ran on GitHub with everything
   built tonight. It worked: the GTA 6 watchlist measured "surging" (80 news articles in 24 hours, 18,007 Wikipedia views
   against 16,324 usual) and gave it 3 places; fact packs got 3 second opinions; covered topics were skipped; Claude
   edited 3 boards and wrote 2 (usage counted: 3 of 12 edits, 2 of 4 writes); the first GTA 6 Short was written ("GTA 6
   has no disc, so what will it cost you?"). The fact check stopped one GTA board that claimed pre-orders start next
   week, which the sources didn't say. Exactly what it is for.
2. **Clip money counts Instagram.** Each clip's Instagram Reel is submitted and paid as its own post, so the money
   estimates (hub, clips page, money alert) now count it once it has views over the campaign's minimum.
3. **An expired sign-in no longer stops everything.** If Google ever expires or revokes one of the YouTube sign-ins, the
   identity guard used to treat it as "a sign-in outside the studio account" and stop every posting job. Now it is
   marked "expired sign-in", posting elsewhere carries on, and a separate issue asks you to reconnect it. (Checked: none of
   the four sign-ins has an expiry date, so this is a safety net, not a live problem.)
4. **Competitor research fixed after its first real run.** It searched "gaming" and "movie" and got Spanish, Hindi and
   Indonesian film recaps. It now searches Shorts like ours ("music facts", "football facts", one per category, US
   region), keeps English titles only, and a day the YouTube allowance cut short is finished by the next run.
5. **No more Shorts about "movie times".** A practical search ("movie times", showtimes, near me, login, weather) has no
   story in it; the topic pickers now skip them.
6. **The watchlist now covers the next big dated events, not only GTA 6.** Avengers: Doomsday and Dune: Part Three
   (both out 18 December) and The Game Awards (10 December). Each starts its build-up at its own lead time (films 30
   days out, The Game Awards 21, GTA 6 45) and turns "surging" the moment a trailer or big news lands, whatever the date.
   Items far off and quiet are only measured, so the list can grow without taking forced Shorts a day.
7. **The clips' spoken take is confirmed working on GitHub, and the 11 test clips are not wasted.** Tonight's private
   test made 11 clips: 9 with the voice reading our own intro and reaction ("Watch as Mitch plots his next big move" ...
   "Did his strategy surprise you? What do you think?"), 2 as on-screen text because Speed's campaign avoids AI. They
   were private, so a new "promote" step puts them into Saturday's 19:00 batch like any other clip (posted, submitted,
   counted in the day). YouTube's daily allowance was nearly used when it ran, so it finishes in the 10:00 run. The same job's installs stalled for 37 minutes on a slow mirror; installs now retry with time
   limits and the clips step always leaves time to save its work.
8. **Two campaigns were making no clips; fixed.** valorant-champs and kevin-langue-ghost got "no moments" every run:
   two free models replied with nothing, the system read that as an empty answer instead of asking the next model, and
   the Valorant stream (144 minutes) was too long for one request anyway. Empty replies now go straight to the next model
   (this also protects fact packs and the writer), and long streams are planned in 45-minute windows, the least
   clipped stretch first.
9. **No more empty clip places.** When a campaign has nothing left to clip (the finished Valorant series) or finds no
   moments, its places for the day now go to the campaigns on the same channel that filled theirs, strongest first.
10. **The YouTube allowance was closer to running out than the system knew.** YouTube gives the project 10,000 units a
   day, shared by the Shorts and the clips. The guard that protects the Shorts' uploads never saw them (their record was
   thrown away after each upload job), so it thought 7,666 were spent when the real figure was about 9,200. Fixed: the
   Shorts' uploads are counted, the guard keeps room for the 15 planned Shorts (not the 40 ceiling), and clips upload
   only from what the Shorts don't need (a clip that doesn't fit waits for the next run). Clips grew to 53 uploads a
   day, so this would have started failing Shorts within days.
11. **The two newer clip channels were about to make 12 fewer clips a day.** When YouTube refused an upload, the system
   recorded how many clips were booked for the next batch instead of how many YouTube had taken that day, so irl and
   gaming (refused after 10 uploads each) learned a limit of 4. Fixed and reset to 10.

## What needs Charlie

1. **Submit last night's Vyro clips by hand (5 minutes).** The Mac Chrome job failed at 19:07 and 22:07 with "usage
   limit reached" (your Claude allowance), so the evening's Vyro submissions were not made. Open
   https://quickplay-studio.github.io/quickplay-autopilot/submit.html on your phone and submit the rows not marked done.
2. **Check your Claude allowance before 19:00:** https://claude.ai/settings/usage. Tonight's session used a lot of it,
   and the Mac Chrome job needs some left at 19:00 to submit the day's clips.
3. **Optional, more free writing power:** two free providers are wired in but have no key. Sign in with the studio
   Google account, make a key, and add it as a repository secret (both names are already on the identity allowlist):
   - Cerebras: https://cloud.cerebras.ai, key name CEREBRAS_API_KEY
   - Mistral: https://console.mistral.ai, key name MISTRAL_API_KEY
   - add each at https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions
4. **Optional, more YouTube allowance:** Google raises the 10,000 units a day for free after an audit form, which takes
   a few weeks: https://support.google.com/youtube/contact/yt_api_form (sign in with the studio account; describe the
   automation as it is). The clips and the Shorts share the one allowance; with more, clips can keep growing.
5. Nothing else. The 11 promoted clips go public with Saturday's 19:00 batch on their own.

Checked and fine, no action: YouTube's AI disclosure rule covers realistic people, events and AI music, not a
narrator voice reading our own script, so the Shorts and clips stay undisclosed (disclosing would not cut reach either:
https://support.google.com/youtube/answer/14328491).

## Ideas to research or decide (things Claude could not do tonight)

1. **Automatic dubbing** (Spanish, Portuguese, Hindi, French and more): India alone is 10.5% of our views. There is no
   API for it, so check whether the channel has it: YouTube Studio > Settings > Upload defaults > Advanced settings >
   "Allow automatic dubbing".
2. **TikTok Creator Rewards** pays in the UK from 10,000 followers and 100,000 views in 30 days, for videos of 1 minute
   or more. Our Shorts run about 30 seconds; a 60 to 90 second TikTok cut is worth testing once the account has followers.
3. **Facebook Content Monetization** is by invitation: look in the Quickplay page's Professional Dashboard >
   Monetisation for an invite.
4. **A second-language channel** (Spanish or Hindi): the same pipeline with translated scripts and a native voice, all
   free. Worth a demand check in vidIQ's keyword tool before building.
5. **More paid-clip platforms** besides Vyro and Content Rewards (Vues and Klippify were named in the research):
   check which pay UK creators and allow YouTube Shorts, then join with the studio account; the scout adds them after.
6. **The 2027 Partner Programme route:** from 1 February 2027 it needs 20M Shorts views in 90 days or 8,000 long-form
   watch hours in a year. The weekly compilation is a start; longer compilations (10 minutes or more per category) are
   the other road.
7. **Decisions only you can make** (each breaks a current rule, so not done): US spelling in titles (40% of views are
   American; the rule says UK English); "money facts, never advice" Shorts (records, prices, most expensive) under the
   "never money" rule.
