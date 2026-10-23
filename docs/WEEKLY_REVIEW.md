# Weekly improvement review (a Claude scheduled task)

The automation tests, measures and adapts by itself every day. Once a week a Claude session reads everything it measured,
fixes what broke, acts on rule changes and starts the next test. Claude could not create this task itself (the app's
permission check), so Charlie creates it once: in the Claude app, Scheduled tasks, New task, every Monday at 10:13 UK,
with the prompt below. It uses one Claude session a week.

## Prompt

Quickplay weekly improvement review (Monday 10:13 UK). Goal: more views, subscribers, retention and money every week,
adapting to YouTube's algorithm and rule changes, with as little of Charlie's time as possible.

Attach the GitHub repo quickplay-studio/quickplay-autopilot with push access (add_repo), clone it as the tool says,
register it, and read CLAUDE.md (its rules bind). Keep token use low: head, grep or short scripts, never data files whole.

Read: analytics/weekly.md, status/funnel.json and the last 14 rows of analytics/funnel.csv, open GitHub issues (labels
alert and policy), the tail of docs/POLICY.md, analytics/decisions.csv (last 20 lines and any check_on date now due),
analytics/drivers.csv verdicts, analytics/models.json, analytics/slots.json "bands", clips/insights.json, status/volume.json,
status/claude_usage.json, the last 15 lines of docs/NEXT.md and docs/CLIPS.md.

Then, from the data only:
1. Fix the root cause of anything that broke or stalled this week (funnel stuck stages, alerts, failed runs).
2. For each open policy issue, change the pipeline to fit (or note why no change is needed) and close it with one line.
3. Pick the biggest lever toward money (Partner Programme: 1,000 subscribers and, from 1 February 2027, 20 million Shorts
   views in 90 days or 8,000 long-form watch hours in 365 days; clip campaigns: clips over each campaign's minimum views).
   Make at most two changes, each a measured test with its metric and judging date, logged in docs/NEXT.md (or
   docs/CLIPS.md) and analytics/decisions.csv (check_on).
4. Judge any test whose check_on date has passed: keep, undo or extend, logged the same way.

Run tests/, push. Finish with ONE SendUserMessage of at most six lines: the week's numbers (views, subscribers, clips
submitted, money estimate), what broke and was fixed, what changed and why, and anything only Charlie can do (with links).
