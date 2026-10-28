# The joint model (every test factor at once)

Updated 2026-10-28. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 166 Shorts, 61 columns, residual spread 1.507, effective parameters 15.3
- engaged: 140 Shorts, 40 columns, residual spread 0.298, effective parameters 26.7

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| replies | on | views | 1.232x | 0.917x to 1.642x | 70 | no |
| title_emoji | none | views | 1.226x | 0.944x to 1.581x | 20 | no |
| fx_slot | 06:00 to 12:00 | views | 1.15x | 0.927x to 1.348x | 13 | no |
| hook_type | number | engaged | 1.149x | 0.931x to 1.364x | 8 | no |
| title_search | search phrase | views | 1.125x | 0.88x to 1.45x | 22 | no |
| ending | question | views | 1.118x | 0.927x to 1.368x | 14 | no |
| first_frame | cover | engaged | 1.094x | 0.884x to 1.435x | 18 | no |
| franchise | named | views | 1.091x | 0.872x to 1.31x | 12 | no |
| sub_push | none | views | 1.091x | 0.94x to 1.304x | 12 | no |
| gene:g003 | b | views | 1.067x | 0.935x to 1.222x | 4 | no |
| length | 25 to 34 s | views | 1.057x | 0.802x to 1.414x | 19 | no |
| fx_opening | lab | views | 1.028x | 0.887x to 1.132x | 6 | no |

## Interactions whose interval clears no difference

2 of 38 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Gaming: stated on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.949x to 0.997x, 8 Shorts; q 0.664, fails the luck check
- Gaming: held back on title_answer (views): 1.033x beyond its usual effect, 90% interval 1.003x to 1.054x, 4 Shorts; q 0.664, fails the luck check

## Controls

- exploration Short: 0.723x (0.368x to 1.557x)
- topic heat (per point): 1.03x (0.847x to 1.315x)
