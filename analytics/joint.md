# The joint model (every test factor at once)

Updated 2026-10-28. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 164 Shorts, 61 columns, residual spread 1.508, effective parameters 15.1
- engaged: 140 Shorts, 40 columns, residual spread 0.298, effective parameters 26.7

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| replies | on | views | 1.254x | 0.94x to 1.617x | 68 | no |
| title_emoji | none | views | 1.176x | 0.903x to 1.482x | 20 | no |
| hook_type | number | engaged | 1.149x | 0.931x to 1.364x | 8 | no |
| title_search | search phrase | views | 1.131x | 0.902x to 1.51x | 20 | no |
| fx_slot | 06:00 to 12:00 | views | 1.13x | 0.889x to 1.38x | 13 | no |
| ending | question | views | 1.106x | 0.894x to 1.287x | 13 | no |
| first_frame | cover | engaged | 1.094x | 0.884x to 1.435x | 18 | no |
| length | 25 to 34 s | views | 1.069x | 0.769x to 1.384x | 18 | no |
| sub_push | none | views | 1.066x | 0.854x to 1.256x | 12 | no |
| first_frame | photo | views | 1.052x | 0.767x to 1.432x | 22 | no |
| fx_grade | natural | views | 1.051x | 0.943x to 1.174x | 5 | no |
| fx_opening | lab | views | 1.044x | 0.925x to 1.175x | 5 | no |

## Interactions whose interval clears no difference

0 of 38 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- none yet

## Controls

- exploration Short: 0.72x (0.293x to 1.628x)
- topic heat (per point): 1.025x (0.876x to 1.257x)
