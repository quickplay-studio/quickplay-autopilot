# Quickplay weekly review (Sundays, 17:50 UK)

Make next week's Shorts look, sound and play better than this week's, from this week's numbers. Spend tokens on
judgement, not browsing. Channel rules in CLAUDE.md still apply (no dashes, UK style, family-friendly).

1. `git pull`. Read analytics/insights.md, analytics/looks.json, analytics/summary.json, templates/looks.json and
   templates/formats.json. Skim this week's boards (boards/done: title, format, look in status/<id>.json).
2. **Looks** (how a Short looks and sounds; GitHub already leans towards the winners each day):
   - Retire an option scoring under 0.85 over 8 or more Shorts: keep it in templates/looks.json with
     `"retired": "<date>: <why, with numbers>"`. Never retire the last active option of a dimension.
   - Open review/<id>.jpg (frame strips) for the 3 best and 3 worst Shorts by `look_score` in analytics/shorts.csv.
     Note what the best share (caption size and position, framing, movement, colour, how busy the screen is) and what
     the worst share.
   - Add at most ONE new option, in one dimension, from what the best share or from a standout Short in our niches
     (vidIQ outliers if the vidIQ account has credits, otherwise the YouTube charts in trends/latest.json: copy the
     style, never footage). Caption styles: `body.cap-<id>` rules in pipeline/template3.html
     plus the option in templates/looks.json. Grades: a CSS filter and vignette. Energy: motion, punch, beat_punches.
     New voices need a reference recording: ask Charlie instead.
   - Test every template change before keeping it: copy boards/test/TEST-L1.json to boards/queue/TEST-W<MMDD>.json
     (mode "none", `look` set to the new option), push, wait for status/TEST-W<MMDD>.json (about 20 minutes), open
     review/TEST-W<MMDD>.jpg. If it failed or looks wrong, revert the change. Move the test board to boards/test/.
3. **Where viewers leave** (insights): if one kind of beat loses viewers clearly faster than footage, make one fix
   (shorter holds on stat cards, a quicker reveal, fewer words on screen) in the template or in CLAUDE.md's guidance,
   tested the same way.
4. **Formats**: retire a format whose Shorts got under 0.6 of the channel's median views over 5 or more Shorts (move it
   to "retired" in templates/formats.json with the reason). Add at most one new format modelled on a vidIQ outlier in
   our categories, or on the YouTube charts when vidIQ has no credits (structure and pacing only). Change CLAUDE.md's "What gets views" only for lessons the numbers show.
5. **Reserve**: keep 5 approved evergreen Shorts in boards/reserve (status "in reserve (approved)"). If there are fewer,
   write the missing ones (CLAUDE.md rules, `"reserve": true`, topics that stay true for months: science, nature,
   records, music and film history), push them, and once they render add their previews to the message below with
   "Reply: reserve approve all, or reserve reject QD-0xx."
6. One commit ("Weekly review <date>: ..."), push. Then send Charlie ONE message of at most 6 lines: what changed and
   why (with the numbers), and what's being tried next week. Finish with that.
