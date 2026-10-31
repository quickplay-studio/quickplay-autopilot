# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 193 Shorts, 98 columns, residual spread 1.564, effective parameters 18.8
- engaged: 184 Shorts, 87 columns, residual spread 0.332, effective parameters 42.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.276x | 0.993x to 1.561x | 14 | no |
| gene:g004 | b | engaged | 1.265x | 0.91x to 1.588x | 5 | no |
| fx_grade | natural | views | 1.25x | 0.954x to 1.5x | 18 | no |
| fx_energy | lab | views | 1.197x | 0.891x to 1.485x | 20 | no |
| replies | on | views | 1.153x | 0.939x to 1.5x | 86 | no |
| title_emoji | none | views | 1.142x | 0.904x to 1.43x | 36 | no |
| sub_push | none | views | 1.141x | 0.894x to 1.39x | 23 | no |
| writer_arm | gemini flash | views | 1.128x | 0.984x to 1.261x | 8 | no |
| fx_slot | 06:00 to 12:00 | views | 1.116x | 0.859x to 1.467x | 25 | no |
| franchise | named | views | 1.108x | 0.854x to 1.436x | 20 | no |
| title_search | search phrase | views | 1.099x | 0.852x to 1.408x | 32 | no |
| length | 25 to 34 s | views | 1.082x | 0.807x to 1.336x | 31 | no |

## Interactions whose interval clears no difference

20 of 114 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: off on replies (views): 0.952x beyond its usual effect, 90% interval 0.919x to 0.996x, 9 Shorts; q 0.242, fails the luck check
- Entertainment: on on replies (views): 1.05x beyond its usual effect, 90% interval 1.004x to 1.088x, 10 Shorts; q 0.242, fails the luck check
- Sport: b on gene:g003 (views): 0.957x beyond its usual effect, 90% interval 0.94x to 0.99x, 4 Shorts; q 0.131, fails the luck check
- Sport: a on gene:g003 (views): 1.044x beyond its usual effect, 90% interval 1.01x to 1.064x, 3 Shorts; q 0.131, fails the luck check
- Sport: named on franchise (views): 0.963x beyond its usual effect, 90% interval 0.942x to 0.996x, 3 Shorts; q 0.137, fails the luck check
- Sport: plain on franchise (views): 1.038x beyond its usual effect, 90% interval 1.004x to 1.062x, 4 Shorts; q 0.137, fails the luck check
- Music: photo on first_frame (views): 0.964x beyond its usual effect, 90% interval 0.933x to 0.998x, 5 Shorts; q 0.318, fails the luck check
- Music: cover on first_frame (views): 1.037x beyond its usual effect, 90% interval 1.002x to 1.072x, 4 Shorts; q 0.318, fails the luck check
- Gaming: stated on title_answer (views): 0.965x beyond its usual effect, 90% interval 0.951x to 0.995x, 10 Shorts; q 0.137, fails the luck check
- Sport: statement on hook_type (views): 0.965x beyond its usual effect, 90% interval 0.943x to 0.998x, 6 Shorts; q 0.242, fails the luck check
- Gaming: held back on title_answer (views): 1.036x beyond its usual effect, 90% interval 1.005x to 1.052x, 4 Shorts; q 0.137, fails the luck check
- Sport: number on hook_type (views): 1.036x beyond its usual effect, 90% interval 1.002x to 1.06x, 6 Shorts; q 0.242, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.967x beyond its usual effect, 90% interval 0.954x to 0.991x, 6 Shorts; q 0.131, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.034x beyond its usual effect, 90% interval 1.009x to 1.049x, 3 Shorts; q 0.131, fails the luck check
- Gaming: steady on fx_energy (views): 0.968x beyond its usual effect, 90% interval 0.952x to 0.992x, 9 Shorts; q 0.137, fails the luck check

## Controls

- exploration Short: 0.938x (0.427x to 1.813x)
- topic heat (per point): 0.955x (0.764x to 1.19x)
