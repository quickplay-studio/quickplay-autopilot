# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 192 Shorts, 95 columns, residual spread 1.569, effective parameters 18.6
- engaged: 184 Shorts, 87 columns, residual spread 0.332, effective parameters 42.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| gene:g004 | b | engaged | 1.265x | 0.91x to 1.588x | 5 | no |
| fx_opening | lab | views | 1.264x | 0.984x to 1.532x | 13 | no |
| fx_grade | natural | views | 1.26x | 0.985x to 1.543x | 18 | no |
| fx_energy | lab | views | 1.191x | 0.872x to 1.505x | 19 | no |
| replies | on | views | 1.149x | 0.889x to 1.445x | 85 | no |
| sub_push | none | views | 1.143x | 0.89x to 1.381x | 23 | no |
| title_emoji | none | views | 1.133x | 0.876x to 1.45x | 35 | no |
| writer_arm | gemini flash | views | 1.128x | 0.993x to 1.224x | 8 | no |
| fx_slot | 06:00 to 12:00 | views | 1.105x | 0.876x to 1.394x | 24 | no |
| franchise | named | views | 1.096x | 0.882x to 1.432x | 19 | no |
| title_search | search phrase | views | 1.093x | 0.843x to 1.465x | 31 | no |
| length | 25 to 34 s | views | 1.086x | 0.834x to 1.417x | 31 | no |

## Interactions whose interval clears no difference

14 of 108 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.054x beyond its usual effect, 90% interval 1.001x to 1.11x, 18 Shorts; q 0.369, fails the luck check
- Music: on on replies (views): 0.949x beyond its usual effect, 90% interval 0.901x to 0.999x, 11 Shorts; q 0.369, fails the luck check
- Entertainment: off on replies (views): 0.952x beyond its usual effect, 90% interval 0.919x to 0.991x, 9 Shorts; q 0.265, fails the luck check
- Entertainment: on on replies (views): 1.05x beyond its usual effect, 90% interval 1.009x to 1.089x, 10 Shorts; q 0.265, fails the luck check
- Gaming: held back on title_answer (views): 1.036x beyond its usual effect, 90% interval 1.005x to 1.053x, 4 Shorts; q 0.171, fails the luck check
- Gaming: stated on title_answer (views): 0.966x beyond its usual effect, 90% interval 0.95x to 0.995x, 10 Shorts; q 0.171, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.967x beyond its usual effect, 90% interval 0.95x to 0.989x, 6 Shorts; q 0.171, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.034x beyond its usual effect, 90% interval 1.011x to 1.053x, 3 Shorts; q 0.171, fails the luck check
- Gaming: steady on fx_energy (views): 0.968x beyond its usual effect, 90% interval 0.952x to 0.991x, 9 Shorts; q 0.171, fails the luck check
- Gaming: lab on fx_energy (views): 1.033x beyond its usual effect, 90% interval 1.009x to 1.05x, 4 Shorts; q 0.171, fails the luck check
- Entertainment: stated on title_answer (views): 1.03x beyond its usual effect, 90% interval 1.005x to 1.053x, 3 Shorts; q 0.265, fails the luck check
- Entertainment: held back on title_answer (views): 0.971x beyond its usual effect, 90% interval 0.95x to 0.995x, 8 Shorts; q 0.265, fails the luck check
- Entertainment: shown on angles (views): 0.972x beyond its usual effect, 90% interval 0.957x to 0.992x, 5 Shorts; q 0.171, fails the luck check
- Entertainment: hidden on angles (views): 1.028x beyond its usual effect, 90% interval 1.008x to 1.045x, 3 Shorts; q 0.171, fails the luck check

## Controls

- exploration Short: 0.939x (0.433x to 1.588x)
- topic heat (per point): 0.953x (0.763x to 1.182x)
