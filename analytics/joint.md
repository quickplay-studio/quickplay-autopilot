# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 190 Shorts, 93 columns, residual spread 1.543, effective parameters 18.5
- engaged: 154 Shorts, 44 columns, residual spread 0.296, effective parameters 29.5

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.29x | 0.97x to 1.524x | 12 | no |
| fx_energy | lab | views | 1.252x | 0.978x to 1.567x | 17 | no |
| hook_type | number | engaged | 1.231x | 0.994x to 1.459x | 11 | no |
| fx_grade | natural | views | 1.214x | 0.948x to 1.533x | 17 | no |
| length | 25 to 34 s | views | 1.173x | 0.849x to 1.462x | 31 | no |
| fx_slot | 06:00 to 12:00 | views | 1.164x | 0.862x to 1.51x | 22 | no |
| sub_push | none | views | 1.163x | 0.898x to 1.444x | 21 | no |
| writer_arm | gemini flash | views | 1.135x | 0.997x to 1.251x | 8 | no |
| title_answer | held back | views | 1.1x | 0.859x to 1.426x | 22 | no |
| replies | on | views | 1.089x | 0.809x to 1.392x | 82 | no |
| title_emoji | none | views | 1.086x | 0.867x to 1.333x | 32 | no |
| first_frame | cover | engaged | 1.076x | 0.897x to 1.334x | 24 | no |

## Interactions whose interval clears no difference

14 of 92 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.068x beyond its usual effect, 90% interval 1.001x to 1.118x, 18 Shorts; q 0.269, fails the luck check
- Music: on on replies (views): 0.937x beyond its usual effect, 90% interval 0.895x to 0.999x, 10 Shorts; q 0.269, fails the luck check
- Entertainment: on on replies (views): 1.056x beyond its usual effect, 90% interval 1.007x to 1.1x, 10 Shorts; q 0.269, fails the luck check
- Entertainment: off on replies (views): 0.947x beyond its usual effect, 90% interval 0.909x to 0.993x, 9 Shorts; q 0.269, fails the luck check
- Music: photo on first_frame (views): 0.951x beyond its usual effect, 90% interval 0.932x to 0.993x, 4 Shorts; q 0.223, fails the luck check
- Music: cover on first_frame (views): 1.051x beyond its usual effect, 90% interval 1.007x to 1.073x, 4 Shorts; q 0.223, fails the luck check
- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.93x to 0.988x, 4 Shorts; q 0.223, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.012x to 1.075x, 6 Shorts; q 0.223, fails the luck check
- Gaming: stated on title_answer (views): 0.959x beyond its usual effect, 90% interval 0.946x to 0.985x, 10 Shorts; q 0.019, passes the luck check
- Gaming: held back on title_answer (views): 1.042x beyond its usual effect, 90% interval 1.015x to 1.057x, 3 Shorts; q 0.019, passes the luck check
- Sport: stated on title_answer (views): 0.962x beyond its usual effect, 90% interval 0.942x to 0.992x, 5 Shorts; q 0.223, fails the luck check
- Sport: held back on title_answer (views): 1.039x beyond its usual effect, 90% interval 1.008x to 1.062x, 4 Shorts; q 0.223, fails the luck check
- Entertainment: shown on angles (views): 0.976x beyond its usual effect, 90% interval 0.962x to 0.998x, 5 Shorts; q 0.269, fails the luck check
- Entertainment: hidden on angles (views): 1.024x beyond its usual effect, 90% interval 1.002x to 1.04x, 3 Shorts; q 0.269, fails the luck check

## Controls

- exploration Short: 0.832x (0.469x to 1.627x)
- topic heat (per point): 0.954x (0.787x to 1.157x)
