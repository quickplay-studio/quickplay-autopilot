# The joint model (every test factor at once)

Updated 2026-10-28. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 165 Shorts, 61 columns, residual spread 1.504, effective parameters 15.2
- engaged: 140 Shorts, 40 columns, residual spread 0.298, effective parameters 26.7

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| replies | on | views | 1.249x | 0.955x to 1.624x | 69 | no |
| title_emoji | none | views | 1.187x | 0.952x to 1.453x | 20 | no |
| hook_type | number | engaged | 1.149x | 0.931x to 1.364x | 8 | no |
| fx_slot | 06:00 to 12:00 | views | 1.133x | 0.909x to 1.424x | 13 | no |
| title_search | search phrase | views | 1.132x | 0.905x to 1.435x | 21 | no |
| ending | question | views | 1.095x | 0.888x to 1.321x | 14 | no |
| first_frame | cover | engaged | 1.094x | 0.884x to 1.435x | 18 | no |
| length | 25 to 34 s | views | 1.073x | 0.797x to 1.387x | 18 | no |
| sub_push | none | views | 1.064x | 0.877x to 1.275x | 12 | no |
| franchise | named | views | 1.059x | 0.85x to 1.317x | 12 | no |
| fx_grade | natural | views | 1.052x | 0.929x to 1.196x | 5 | no |
| fx_opening | lab | views | 1.05x | 0.905x to 1.159x | 5 | no |

## Interactions whose interval clears no difference

0 of 38 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- none yet

## Controls

- exploration Short: 0.691x (0.328x to 1.511x)
- topic heat (per point): 1.025x (0.834x to 1.258x)
