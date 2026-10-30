# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 192 Shorts, 95 columns, residual spread 1.555, effective parameters 18.6
- engaged: 173 Shorts, 66 columns, residual spread 0.306, effective parameters 37.2

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.294x | 1.012x to 1.53x | 12 | yes |
| fx_energy | lab | views | 1.227x | 0.912x to 1.499x | 18 | no |
| fx_opening | image_first | engaged | 1.223x | 0.94x to 1.634x | 7 | no |
| fx_grade | natural | views | 1.185x | 0.898x to 1.426x | 17 | no |
| sub_push | none | views | 1.178x | 0.92x to 1.434x | 23 | no |
| fx_slot | 06:00 to 12:00 | views | 1.176x | 0.903x to 1.487x | 24 | no |
| title_emoji | none | views | 1.17x | 0.89x to 1.482x | 33 | no |
| length | 25 to 34 s | views | 1.155x | 0.862x to 1.46x | 31 | no |
| writer_arm | gemini flash | views | 1.139x | 1.004x to 1.244x | 7 | yes |
| franchise | named | views | 1.135x | 0.888x to 1.389x | 19 | no |
| replies | on | views | 1.13x | 0.857x to 1.484x | 83 | no |
| title_answer | held back | views | 1.111x | 0.834x to 1.402x | 24 | no |

## Interactions whose interval clears no difference

14 of 102 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.054x beyond its usual effect, 90% interval 1.012x to 1.095x, 10 Shorts; q 0.273, fails the luck check
- Entertainment: off on replies (views): 0.949x beyond its usual effect, 90% interval 0.913x to 0.988x, 9 Shorts; q 0.273, fails the luck check
- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.936x to 0.991x, 4 Shorts; q 0.273, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.009x to 1.068x, 6 Shorts; q 0.273, fails the luck check
- Sport: stated on title_answer (views): 0.962x beyond its usual effect, 90% interval 0.944x to 0.996x, 5 Shorts; q 0.273, fails the luck check
- Sport: held back on title_answer (views): 1.039x beyond its usual effect, 90% interval 1.004x to 1.059x, 4 Shorts; q 0.273, fails the luck check
- Gaming: stated on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.949x to 0.995x, 9 Shorts; q 0.273, fails the luck check
- Gaming: held back on title_answer (views): 1.033x beyond its usual effect, 90% interval 1.005x to 1.053x, 4 Shorts; q 0.273, fails the luck check
- Gaming: lab on fx_energy (views): 1.03x beyond its usual effect, 90% interval 1.004x to 1.048x, 4 Shorts; q 0.273, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.971x beyond its usual effect, 90% interval 0.951x to 0.998x, 6 Shorts; q 0.346, fails the luck check
- Gaming: steady on fx_energy (views): 0.971x beyond its usual effect, 90% interval 0.955x to 0.996x, 8 Shorts; q 0.273, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.029x beyond its usual effect, 90% interval 1.002x to 1.051x, 3 Shorts; q 0.346, fails the luck check
- Entertainment: hidden on angles (views): 1.024x beyond its usual effect, 90% interval 1.003x to 1.039x, 3 Shorts; q 0.299, fails the luck check
- Entertainment: shown on angles (views): 0.977x beyond its usual effect, 90% interval 0.962x to 0.997x, 5 Shorts; q 0.299, fails the luck check

## Controls

- exploration Short: 0.828x (0.47x to 1.563x)
- topic heat (per point): 0.927x (0.768x to 1.13x)
