# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 188 Shorts, 88 columns, residual spread 1.574, effective parameters 18.0
- engaged: 155 Shorts, 48 columns, residual spread 0.301, effective parameters 30.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.339x | 0.984x to 1.539x | 12 | no |
| fx_energy | lab | views | 1.29x | 0.927x to 1.6x | 14 | no |
| title_emoji | none | views | 1.257x | 0.936x to 1.513x | 31 | no |
| fx_grade | natural | views | 1.238x | 0.961x to 1.526x | 16 | no |
| title_answer | held back | views | 1.221x | 0.889x to 1.545x | 22 | no |
| first_frame | cover | engaged | 1.186x | 0.953x to 1.482x | 25 | no |
| writer_arm | gemini flash | views | 1.171x | 1.029x to 1.281x | 7 | yes |
| fx_slot | 06:00 to 12:00 | views | 1.159x | 0.88x to 1.461x | 21 | no |
| sub_push | none | views | 1.159x | 0.902x to 1.423x | 22 | no |
| franchise | named | views | 1.152x | 0.862x to 1.428x | 19 | no |
| length | 25 to 34 s | views | 1.125x | 0.843x to 1.477x | 29 | no |
| hook_type | number | engaged | 1.119x | 0.926x to 1.314x | 13 | no |

## Interactions whose interval clears no difference

16 of 86 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.054x beyond its usual effect, 90% interval 1.011x to 1.111x, 18 Shorts; q 0.311, fails the luck check
- Music: on on replies (views): 0.949x beyond its usual effect, 90% interval 0.9x to 0.989x, 11 Shorts; q 0.311, fails the luck check
- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.937x to 0.985x, 4 Shorts; q 0.116, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.015x to 1.068x, 5 Shorts; q 0.116, fails the luck check
- Gaming: on on replies (views): 1.045x beyond its usual effect, 90% interval 1.003x to 1.089x, 19 Shorts; q 0.311, fails the luck check
- Gaming: off on replies (views): 0.957x beyond its usual effect, 90% interval 0.918x to 0.997x, 14 Shorts; q 0.311, fails the luck check
- Sport: held back on title_answer (views): 1.039x beyond its usual effect, 90% interval 1.008x to 1.055x, 3 Shorts; q 0.116, fails the luck check
- Sport: stated on title_answer (views): 0.963x beyond its usual effect, 90% interval 0.948x to 0.992x, 5 Shorts; q 0.116, fails the luck check
- Gaming: steady on fx_energy (views): 0.968x beyond its usual effect, 90% interval 0.956x to 0.995x, 9 Shorts; q 0.116, fails the luck check
- Gaming: lab on fx_energy (views): 1.033x beyond its usual effect, 90% interval 1.005x to 1.046x, 3 Shorts; q 0.116, fails the luck check
- Entertainment: lab on fx_energy (views): 1.031x beyond its usual effect, 90% interval 1.002x to 1.052x, 3 Shorts; q 0.244, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.031x beyond its usual effect, 90% interval 1.001x to 1.055x, 3 Shorts; q 0.308, fails the luck check
- Entertainment: steady on fx_energy (views): 0.97x beyond its usual effect, 90% interval 0.95x to 0.998x, 3 Shorts; q 0.244, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.97x beyond its usual effect, 90% interval 0.948x to 0.999x, 4 Shorts; q 0.308, fails the luck check
- Gaming: held back on title_answer (views): 1.03x beyond its usual effect, 90% interval 1.004x to 1.048x, 4 Shorts; q 0.244, fails the luck check

## Controls

- exploration Short: 0.838x (0.442x to 1.637x)
- topic heat (per point): 0.956x (0.783x to 1.196x)
