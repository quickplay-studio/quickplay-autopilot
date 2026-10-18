# Quickplay review (Wednesdays and Sundays, 17:50 UK)

Charlie has given full discretion: change anything the numbers support (what we cover, formats, hooks, titles, length,
posting times, captions, voice and its speed, camera energy, colour, music, graphics, the TikTok and Instagram picks) to
get the most views and subscribers, as long as the channel rules in CLAUDE.md hold. Every change is data-driven,
explained in plain words with the numbers, logged, and checked a week later. Spend tokens on judgement, not browsing.

1. `git pull`. Read analytics/insights.md (recipe, drivers, timing, regions, traffic), analytics/drivers.csv,
   analytics/decisions.csv, analytics/looks.json, analytics/summary.json, analytics/hourly.csv (last 14 days),
   analytics/geo.csv, analytics/traffic.csv, templates/looks.json and templates/formats.json. In analytics/shorts.csv
   sort by views_vs_typical (each Short against Shorts posted within 3 days of it, 1.0 = typical) and open
   review/<id>.jpg (frame strips) for the 3 best and 3 worst: note what the best share (topic type, hook, title, first
   image, caption size and position, pace, colour, how busy the screen is) and what the worst share.
2. **Check earlier changes.** For every decisions.csv line whose check_on date has passed and has no outcome line yet,
   compare the Shorts since the change with the ones before (views_vs_typical, held at 3 seconds, % viewed). Keep it if
   it helped or made no difference; revert it if it clearly hurt (15% worse or more over 10 or more Shorts). Log the
   outcome as a new line ("Kept: ...", "Reverted: ...").
3. **Decide at most three changes**, biggest expected gain first, each from a result with 5 or more Shorts from 2 or
   more days (drivers.csv "push" or "cut back", a look score, a clear timing peak, or a region or traffic pattern of
   similar strength). One change per area at a time, so each effect can be measured. Test as a split where possible
   (a new option in templates/looks.json, or alternating Shorts). Where each kind of change lives:
   - What we cover: the category mix in the Recipe updates itself; to steer harder (a topic type, a fandom, a kind of
     story) edit "What gets views" in CLAUDE.md.
   - Formats: retire one whose Shorts run under 0.6x typical over 5 or more (move it to "retired" in
     templates/formats.json with the reason); add at most one, modelled on a standout Short in our categories (vidIQ
     outliers if the account has credits, otherwise the YouTube charts in trends/latest.json): structure and pacing only,
     never footage or script.
   - Hooks, titles, length, endings: the rules in "What gets views" in CLAUDE.md (for example the hook style or title
     style the drivers favour, or a new length target).
   - Look and sound (captions, voice, voice speed as an option's "wps", camera energy, grade, opening): add, retire or
     re-weight options in templates/looks.json (plan.py samples them and leans towards winners). Retire an option under
     0.85 over 8 or more Shorts with `"retired": "<date>: <why, with numbers>"`; never the last of a dimension. Caption
     styles are `body.cap-<id>` rules in pipeline/template3.html; grades are a CSS filter and vignette; energy is motion,
     punch and beat_punches. The TikTok and Instagram safe-zone rules (`body.lay-social`) stay. New voices need a
     reference recording: ask Charlie instead.
   - Posting times: config.json slot_first and slot_every_minutes, or analytics/slots.json's learned slots, when
     hourly.csv shows UK hours whose views an hour run 30% or more above the day's average for a week.
   - Where viewers leave: one fix (shorter holds on stat cards, quicker reveals, fewer words on screen) in the template
     or in CLAUDE.md's guidance.
   - TikTok and Instagram picks: the rules in CLAUDE.md, from ig_views and tt_views by category.
   - Volume (Charlie wants the most uploads the data supports): raise daily_limit, slots_per_day and config `runs` by 4
     when the last week's median views per Short held within 10% as volume rose and YouTube refused no uploads; lower
     them if views per Short fell 20% or more. Instagram and Facebook targets (`*_target`) follow their own views per
     Reel the same way; their daily ramp stays as it is.
   Test every template change before keeping it: copy boards/test/TEST-L1.json to boards/queue/TEST-W<MMDD>.json (mode
   "none", `look` set to show the change), push, wait for status/TEST-W<MMDD>.json (about 20 minutes), and open
   review/TEST-W<MMDD>.jpg and review/TEST-W<MMDD>.social.jpg (the TikTok and Instagram layout). If it failed or looks
   wrong, revert the change. Move the test board to boards/test/.
4. **Log** every change and every revert as a new line at the top of analytics/decisions.csv: date, area, change, why
   (the numbers in plain words), evidence (file and figures), check_on (7 days later), by "review".
5. **Reserve**: keep 5 approved evergreen Shorts in boards/reserve (status "in reserve (approved)"). If there are fewer,
   write the missing ones (CLAUDE.md rules, `"reserve": true`, topics that stay true for months: science, nature,
   records, music and film history), push them, and once they render add their previews to the message below with
   "Reply: reserve approve all, or reserve reject QD-0xx." (`python pipeline/previews.py <dir> --reserve`).
6. One commit ("Review <date>: ..."), push. Then send Charlie ONE message of at most 10 lines: each change on one line
   with its reason and the numbers ("Music Shorts got 1.6x typical views over 9 Shorts, so the daily mix moves to 35%
   Music"), what the checks of earlier changes showed, what is being tested next, and anything he could do to help (only
   if there is something real). Finish with that.
