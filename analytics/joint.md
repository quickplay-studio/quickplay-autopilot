# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 190 Shorts, 93 columns, residual spread 1.543, effective parameters 18.5
- engaged: 172 Shorts, 67 columns, residual spread 0.301, effective parameters 37.7

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.288x | 0.97x to 1.526x | 12 | no |
| fx_energy | lab | views | 1.251x | 0.977x to 1.575x | 17 | no |
| fx_grade | natural | views | 1.209x | 0.946x to 1.527x | 17 | no |
| length | 25 to 34 s | views | 1.179x | 0.852x to 1.468x | 31 | no |
| fx_slot | 06:00 to 12:00 | views | 1.164x | 0.864x to 1.51x | 22 | no |
| sub_push | none | views | 1.164x | 0.903x to 1.444x | 21 | no |
| fx_opening | image_first | engaged | 1.157x | 0.937x to 1.448x | 7 | no |
| hook_type | number | engaged | 1.145x | 0.996x to 1.32x | 20 | no |
| writer_arm | gemini flash | views | 1.138x | 0.997x to 1.258x | 8 | no |
| title_answer | held back | views | 1.096x | 0.861x to 1.422x | 22 | no |
| title_emoji | none | views | 1.088x | 0.869x to 1.333x | 32 | no |
| replies | on | views | 1.086x | 0.806x to 1.389x | 82 | no |

## Interactions whose interval clears no difference

12 of 98 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.056x beyond its usual effect, 90% interval 1.006x to 1.099x, 10 Shorts; q 0.269, fails the luck check
- Entertainment: off on replies (views): 0.947x beyond its usual effect, 90% interval 0.91x to 0.994x, 9 Shorts; q 0.269, fails the luck check
- Music: cover on first_frame (views): 1.052x beyond its usual effect, 90% interval 1.007x to 1.074x, 4 Shorts; q 0.217, fails the luck check
- Music: photo on first_frame (views): 0.951x beyond its usual effect, 90% interval 0.931x to 0.993x, 4 Shorts; q 0.217, fails the luck check
- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.93x to 0.988x, 4 Shorts; q 0.217, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.012x to 1.075x, 6 Shorts; q 0.217, fails the luck check
- Gaming: held back on title_answer (views): 1.043x beyond its usual effect, 90% interval 1.015x to 1.058x, 3 Shorts; q 0.016, passes the luck check
- Gaming: stated on title_answer (views): 0.959x beyond its usual effect, 90% interval 0.945x to 0.985x, 10 Shorts; q 0.016, passes the luck check
- Sport: held back on title_answer (views): 1.039x beyond its usual effect, 90% interval 1.008x to 1.061x, 4 Shorts; q 0.238, fails the luck check
- Sport: stated on title_answer (views): 0.963x beyond its usual effect, 90% interval 0.942x to 0.992x, 5 Shorts; q 0.238, fails the luck check
- Entertainment: hidden on angles (views): 1.024x beyond its usual effect, 90% interval 1.002x to 1.039x, 3 Shorts; q 0.269, fails the luck check
- Entertainment: shown on angles (views): 0.977x beyond its usual effect, 90% interval 0.962x to 0.998x, 5 Shorts; q 0.269, fails the luck check

## Controls

- exploration Short: 0.832x (0.47x to 1.63x)
- topic heat (per point): 0.935x (0.771x to 1.138x)
