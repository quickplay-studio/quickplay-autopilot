# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 193 Shorts, 95 columns, residual spread 1.553, effective parameters 18.7
- engaged: 186 Shorts, 88 columns, residual spread 0.324, effective parameters 42.4

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.323x | 1.011x to 1.538x | 12 | yes |
| gene:g004 | b | engaged | 1.273x | 0.91x to 1.575x | 5 | no |
| fx_grade | natural | views | 1.2x | 0.906x to 1.491x | 17 | no |
| title_emoji | none | views | 1.179x | 0.889x to 1.49x | 34 | no |
| sub_push | none | views | 1.177x | 0.898x to 1.4x | 23 | no |
| fx_energy | lab | views | 1.141x | 0.892x to 1.399x | 18 | no |
| franchise | named | views | 1.14x | 0.87x to 1.475x | 19 | no |
| writer_arm | gemini flash | views | 1.137x | 1.001x to 1.264x | 7 | yes |
| fx_slot | 06:00 to 12:00 | views | 1.135x | 0.88x to 1.462x | 24 | no |
| replies | on | views | 1.13x | 0.85x to 1.437x | 84 | no |
| length | 25 to 34 s | views | 1.119x | 0.822x to 1.457x | 31 | no |
| ending | loop | views | 1.087x | 0.822x to 1.346x | 33 | no |

## Interactions whose interval clears no difference

14 of 108 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: off on replies (views): 0.95x beyond its usual effect, 90% interval 0.918x to 0.998x, 9 Shorts; q 0.349, fails the luck check
- Entertainment: on on replies (views): 1.052x beyond its usual effect, 90% interval 1.002x to 1.089x, 10 Shorts; q 0.349, fails the luck check
- Sport: statement on hook_type (views): 0.956x beyond its usual effect, 90% interval 0.933x to 0.994x, 4 Shorts; q 0.225, fails the luck check
- Sport: number on hook_type (views): 1.046x beyond its usual effect, 90% interval 1.006x to 1.072x, 6 Shorts; q 0.225, fails the luck check
- Sport: held back on title_answer (views): 1.038x beyond its usual effect, 90% interval 1.004x to 1.062x, 4 Shorts; q 0.225, fails the luck check
- Sport: stated on title_answer (views): 0.964x beyond its usual effect, 90% interval 0.942x to 0.996x, 5 Shorts; q 0.225, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.006x to 1.058x, 3 Shorts; q 0.225, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.967x beyond its usual effect, 90% interval 0.945x to 0.994x, 6 Shorts; q 0.225, fails the luck check
- Entertainment: stated on title_answer (views): 1.03x beyond its usual effect, 90% interval 1.005x to 1.048x, 3 Shorts; q 0.225, fails the luck check
- Gaming: lab on fx_energy (views): 1.03x beyond its usual effect, 90% interval 1.004x to 1.048x, 4 Shorts; q 0.225, fails the luck check
- Entertainment: held back on title_answer (views): 0.971x beyond its usual effect, 90% interval 0.954x to 0.995x, 8 Shorts; q 0.225, fails the luck check
- Gaming: steady on fx_energy (views): 0.971x beyond its usual effect, 90% interval 0.954x to 0.996x, 8 Shorts; q 0.225, fails the luck check
- Entertainment: hidden on angles (views): 1.028x beyond its usual effect, 90% interval 1.008x to 1.048x, 3 Shorts; q 0.225, fails the luck check
- Entertainment: shown on angles (views): 0.973x beyond its usual effect, 90% interval 0.954x to 0.992x, 5 Shorts; q 0.225, fails the luck check

## Controls

- exploration Short: 0.931x (0.475x to 1.649x)
- topic heat (per point): 0.939x (0.755x to 1.127x)
