# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 184 Shorts, 86 columns, residual spread 1.562, effective parameters 17.9
- engaged: 152 Shorts, 48 columns, residual spread 0.303, effective parameters 29.9

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.362x | 1.023x to 1.632x | 12 | yes |
| fx_energy | lab | views | 1.279x | 0.937x to 1.585x | 13 | no |
| fx_grade | natural | views | 1.277x | 0.966x to 1.563x | 16 | no |
| title_emoji | none | views | 1.248x | 0.954x to 1.564x | 30 | no |
| title_answer | held back | views | 1.207x | 0.887x to 1.485x | 21 | no |
| franchise | named | views | 1.191x | 0.897x to 1.377x | 19 | no |
| first_frame | cover | engaged | 1.189x | 0.948x to 1.441x | 25 | no |
| writer_arm | gemini flash | views | 1.174x | 1.027x to 1.279x | 7 | yes |
| sub_push | none | views | 1.145x | 0.917x to 1.485x | 21 | no |
| fx_slot | 06:00 to 12:00 | views | 1.137x | 0.841x to 1.512x | 20 | no |
| length | 25 to 34 s | views | 1.133x | 0.838x to 1.468x | 29 | no |
| replies | on | views | 1.118x | 0.858x to 1.487x | 78 | no |

## Interactions whose interval clears no difference

12 of 82 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Sport: statement on hook_type (views): 0.953x beyond its usual effect, 90% interval 0.936x to 0.986x, 4 Shorts; q 0.118, fails the luck check
- Sport: number on hook_type (views): 1.049x beyond its usual effect, 90% interval 1.014x to 1.069x, 5 Shorts; q 0.118, fails the luck check
- Gaming: on on replies (views): 1.045x beyond its usual effect, 90% interval 1.001x to 1.088x, 19 Shorts; q 0.398, fails the luck check
- Gaming: off on replies (views): 0.957x beyond its usual effect, 90% interval 0.919x to 0.999x, 14 Shorts; q 0.398, fails the luck check
- Sport: held back on title_answer (views): 1.04x beyond its usual effect, 90% interval 1.009x to 1.057x, 3 Shorts; q 0.14, fails the luck check
- Sport: stated on title_answer (views): 0.962x beyond its usual effect, 90% interval 0.946x to 0.992x, 5 Shorts; q 0.14, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.038x beyond its usual effect, 90% interval 1.003x to 1.058x, 3 Shorts; q 0.226, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.964x beyond its usual effect, 90% interval 0.945x to 0.997x, 3 Shorts; q 0.226, fails the luck check
- Gaming: steady on fx_energy (views): 0.967x beyond its usual effect, 90% interval 0.951x to 0.994x, 9 Shorts; q 0.14, fails the luck check
- Gaming: lab on fx_energy (views): 1.034x beyond its usual effect, 90% interval 1.006x to 1.052x, 3 Shorts; q 0.14, fails the luck check
- Gaming: held back on title_answer (views): 1.031x beyond its usual effect, 90% interval 1.001x to 1.049x, 4 Shorts; q 0.238, fails the luck check
- Gaming: stated on title_answer (views): 0.97x beyond its usual effect, 90% interval 0.953x to 0.999x, 10 Shorts; q 0.238, fails the luck check

## Controls

- exploration Short: 0.835x (0.434x to 1.62x)
- topic heat (per point): 0.958x (0.78x to 1.192x)
