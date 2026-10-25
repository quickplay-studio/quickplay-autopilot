# Creator outreach (25 October 2026)

YouTube buried re-uploaded clips on 1 October 2026 (issue #37), and the rule for the clips line is that footage is only ever
clipped with the creator's permission. The scout finds small creators who already say, in their own words, that clips of their
videos are welcome, so there is someone worth asking. **Nothing is sent by the automation.** It only fills a list; you read it,
decide, and send the message below yourself from the studio account if you want to.

## How the list is made

- `pipeline/outreach.py`, once a week, after the scout in clips.yml (08:35 UTC). At most 3 YouTube searches a run (100 units each,
  and only when `quota.allow` says the day's uploads keep their share), then 1-unit reads for the videos and channels: about 306
  of the 10,000 units a week.
- Each search is one niche (gaming, IRL streamers, music, football) with one phrase ("clips allowed", "clip this", "clipping
  permitted", "clip and post", "use my clips", "clippers welcome"); the three combinations used longest ago go first, so a full
  cycle of 24 takes eight weeks.
- A channel is listed when it has under 50,000 subscribers (and over 500; a hidden count is skipped) and its channel description or
  a video of the last 90 days says one of the phrases, not its opposite ("no clips allowed", "please do not clip this"). Channels
  about gambling, crypto, adult content or politics are left out, like everything else on the channel.
- `clips/outreach.csv`: `channel, url, subscribers, niche, evidence, found_on, status`. `evidence` is the creator's own sentence
  and where it was said (the channel description, or the video's link); `found_on` is the UK day it was found.
- The hub's Clips tab shows the newest rows ("Creators who say clips are allowed"). `python pipeline/outreach.py --force` runs the
  scout now (a request of `outreach` in requests/clips.txt does the same).

## What you do with it

Change `status` in the file (or ask Claude to): `new` (just found), `asked` (message sent), `yes` (written permission received),
`no` (declined or no reply after a fortnight), `skip` (not for us). The scout never changes a status and never lists a channel
twice. A line saying clips are allowed is not permission for us in particular: some creators allow clips with conditions, or
only for fans. So always ask, and keep their reply.

A `yes` is written down before any clip is made. To start clipping a creator who said yes, ask Claude to add them as a campaign
source (a campaign entry in clips/campaigns.json with the creator's own permission as its rules) and pin it to a channel: one
creator or niche to a channel (docs/CLIPS.md, 25 October).

## The message

Polite, short, UK English, asks for written permission, offers credit and a link, says nothing about money. Fill in the name and
the quoted line from the `evidence` column.

> Subject: Could we share short clips of your videos, with your permission?
>
> Hello {name},
>
> We run Quickplay Daily, a small channel that shares short vertical clips of great moments from creators we enjoy. Your {niche}
> videos caught our eye, and we saw that you say clips are welcome ("{evidence}").
>
> Before we post anything, may we ask for your permission in writing? We would cut short clips (under a minute) from your public
> videos and streams and share them on YouTube Shorts and Instagram Reels. Every clip would:
>
> - credit you by name in the caption and on screen,
> - link back to your channel ({url}),
> - stay family friendly, and
> - come down at once if you ever ask us to remove it.
>
> A reply of "yes" is all we need, and you are welcome to tell us which videos are fine and which are not. We will not post
> anything until we hear from you.
>
> Thank you for your time, and for making something worth watching.
>
> The Quickplay Daily team

Rules for the message: nothing about payment or earnings, no pressure, no second message if there is no reply, and nothing
that says who runs the channel (it stays anonymous). If they say no, the row is marked `no` and that is the end of it.
