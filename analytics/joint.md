# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 190 Shorts, 93 columns, residual spread 1.558, effective parameters 18.4
- engaged: 155 Shorts, 48 columns, residual spread 0.301, effective parameters 30.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.298x | 1.016x to 1.576x | 12 | yes |
| fx_grade | natural | views | 1.199x | 0.949x to 1.512x | 17 | no |
| first_frame | cover | engaged | 1.186x | 0.953x to 1.482x | 25 | no |
| fx_energy | lab | views | 1.175x | 0.906x to 1.434x | 16 | no |
| title_emoji | none | views | 1.163x | 0.932x to 1.598x | 32 | no |
| sub_push | none | views | 1.16x | 0.895x to 1.399x | 23 | no |
| fx_slot | 06:00 to 12:00 | views | 1.154x | 0.87x to 1.515x | 23 | no |
| length | 25 to 34 s | views | 1.145x | 0.879x to 1.472x | 30 | no |
| writer_arm | gemini flash | views | 1.14x | 1.003x to 1.246x | 7 | yes |
| franchise | named | views | 1.12x | 0.881x to 1.385x | 20 | no |
| hook_type | number | engaged | 1.119x | 0.926x to 1.314x | 13 | no |
| replies | on | views | 1.117x | 0.874x to 1.423x | 81 | no |

## Interactions whose interval clears no difference

18 of 96 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: on on replies (views): 0.948x beyond its usual effect, 90% interval 0.902x to 0.993x, 11 Shorts; q 0.333, fails the luck check
- Music: off on replies (views): 1.054x beyond its usual effect, 90% interval 1.007x to 1.108x, 18 Shorts; q 0.333, fails the luck check
- Sport: statement on hook_type (views): 0.953x beyond its usual effect, 90% interval 0.934x to 0.991x, 4 Shorts; q 0.099, passes the luck check
- Sport: number on hook_type (views): 1.049x beyond its usual effect, 90% interval 1.009x to 1.071x, 5 Shorts; q 0.099, passes the luck check
- Sport: held back on title_answer (views): 1.041x beyond its usual effect, 90% interval 1.007x to 1.06x, 3 Shorts; q 0.136, fails the luck check
- Sport: stated on title_answer (views): 0.961x beyond its usual effect, 90% interval 0.943x to 0.993x, 5 Shorts; q 0.136, fails the luck check
- Music: photo on first_frame (views): 0.965x beyond its usual effect, 90% interval 0.933x to 0.998x, 5 Shorts; q 0.333, fails the luck check
- Music: cover on first_frame (views): 1.036x beyond its usual effect, 90% interval 1.002x to 1.072x, 4 Shorts; q 0.333, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.967x beyond its usual effect, 90% interval 0.95x to 0.994x, 6 Shorts; q 0.136, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.034x beyond its usual effect, 90% interval 1.006x to 1.052x, 3 Shorts; q 0.136, fails the luck check
- Gaming: stated on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.95x to 0.998x, 10 Shorts; q 0.202, fails the luck check
- Gaming: held back on title_answer (views): 1.033x beyond its usual effect, 90% interval 1.002x to 1.053x, 4 Shorts; q 0.202, fails the luck check
- Gaming: lab on fx_energy (views): 1.032x beyond its usual effect, 90% interval 1.01x to 1.047x, 3 Shorts; q 0.099, passes the luck check
- Gaming: steady on fx_energy (views): 0.969x beyond its usual effect, 90% interval 0.955x to 0.99x, 9 Shorts; q 0.099, passes the luck check
- Entertainment: stated on title_answer (views): 1.03x beyond its usual effect, 90% interval 1.002x to 1.046x, 3 Shorts; q 0.214, fails the luck check

## Controls

- exploration Short: 0.854x (0.469x to 1.693x)
- topic heat (per point): 0.956x (0.785x to 1.164x)
