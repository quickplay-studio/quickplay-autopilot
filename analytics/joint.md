# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 194 Shorts, 98 columns, residual spread 1.553, effective parameters 19.0
- engaged: 184 Shorts, 87 columns, residual spread 0.332, effective parameters 42.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.285x | 1.005x to 1.549x | 14 | yes |
| gene:g004 | b | engaged | 1.265x | 0.91x to 1.588x | 5 | no |
| fx_grade | natural | views | 1.236x | 0.974x to 1.535x | 18 | no |
| sub_push | none | views | 1.182x | 0.922x to 1.463x | 24 | no |
| fx_energy | lab | views | 1.158x | 0.909x to 1.387x | 21 | no |
| title_emoji | none | views | 1.147x | 0.881x to 1.489x | 36 | no |
| replies | on | views | 1.129x | 0.852x to 1.509x | 86 | no |
| writer_arm | gemini flash | views | 1.128x | 1.011x to 1.246x | 8 | yes |
| fx_slot | 06:00 to 12:00 | views | 1.125x | 0.891x to 1.46x | 26 | no |
| franchise | named | views | 1.12x | 0.849x to 1.377x | 21 | no |
| length | 25 to 34 s | views | 1.116x | 0.871x to 1.442x | 31 | no |
| title_search | search phrase | views | 1.073x | 0.826x to 1.387x | 33 | no |

## Interactions whose interval clears no difference

26 of 114 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.054x beyond its usual effect, 90% interval 1.006x to 1.11x, 18 Shorts; q 0.337, fails the luck check
- Music: on on replies (views): 0.949x beyond its usual effect, 90% interval 0.901x to 0.994x, 11 Shorts; q 0.337, fails the luck check
- Entertainment: on on replies (views): 1.053x beyond its usual effect, 90% interval 1.004x to 1.09x, 10 Shorts; q 0.205, fails the luck check
- Entertainment: off on replies (views): 0.95x beyond its usual effect, 90% interval 0.918x to 0.996x, 9 Shorts; q 0.205, fails the luck check
- Sport: number on hook_type (views): 1.045x beyond its usual effect, 90% interval 1.011x to 1.069x, 6 Shorts; q 0.164, fails the luck check
- Sport: statement on hook_type (views): 0.957x beyond its usual effect, 90% interval 0.935x to 0.989x, 7 Shorts; q 0.164, fails the luck check
- Music: photo on first_frame (views): 0.964x beyond its usual effect, 90% interval 0.935x to 0.998x, 5 Shorts; q 0.337, fails the luck check
- Music: cover on first_frame (views): 1.037x beyond its usual effect, 90% interval 1.002x to 1.069x, 4 Shorts; q 0.337, fails the luck check
- Sport: named on franchise (views): 0.965x beyond its usual effect, 90% interval 0.948x to 0.992x, 4 Shorts; q 0.164, fails the luck check
- Sport: plain on franchise (views): 1.036x beyond its usual effect, 90% interval 1.008x to 1.055x, 4 Shorts; q 0.164, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.967x beyond its usual effect, 90% interval 0.952x to 0.992x, 6 Shorts; q 0.164, fails the luck check
- Gaming: stated on title_answer (views): 0.967x beyond its usual effect, 90% interval 0.952x to 0.996x, 10 Shorts; q 0.166, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.034x beyond its usual effect, 90% interval 1.008x to 1.05x, 3 Shorts; q 0.164, fails the luck check
- Gaming: held back on title_answer (views): 1.034x beyond its usual effect, 90% interval 1.004x to 1.051x, 4 Shorts; q 0.166, fails the luck check
- Gaming: steady on fx_energy (views): 0.968x beyond its usual effect, 90% interval 0.953x to 0.994x, 9 Shorts; q 0.164, fails the luck check

## Controls

- exploration Short: 0.95x (0.539x to 1.815x)
- topic heat (per point): 0.95x (0.771x to 1.153x)
