# The channel-day subscriber model (advisory only)

Updated 2026-10-28. pipeline/subs_daily.py: a ridge regression of subscribers gained per 1,000 views on the day's mix, within channel, weighted by views, over channel-days with 100 or more views. Nothing reads it yet. YouTube Analytics counts its days in Pacific time, the Shorts columns are UK days, so a day's subscribers can include the end of the day before.

Channel-days used: 11.

Not enough yet: it needs 20 channel-days with 100 or more views and a spread in the mix (4 for each factor), and has 11. The factors' shares are in analytics/subs_daily.csv.
