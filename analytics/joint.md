# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 189 Shorts, 92 columns, residual spread 1.558, effective parameters 18.2
- engaged: 155 Shorts, 48 columns, residual spread 0.301, effective parameters 30.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.274x | 0.985x to 1.518x | 12 | no |
| fx_grade | natural | views | 1.248x | 0.923x to 1.51x | 16 | no |
| first_frame | cover | engaged | 1.186x | 0.953x to 1.482x | 25 | no |
| title_emoji | none | views | 1.181x | 0.894x to 1.505x | 31 | no |
| fx_slot | 06:00 to 12:00 | views | 1.174x | 0.904x to 1.549x | 22 | no |
| fx_energy | lab | views | 1.169x | 0.907x to 1.444x | 15 | no |
| franchise | named | views | 1.16x | 0.864x to 1.457x | 19 | no |
| writer_arm | gemini flash | views | 1.153x | 1.009x to 1.275x | 7 | yes |
| replies | on | views | 1.14x | 0.876x to 1.451x | 80 | no |
| hook_type | number | engaged | 1.119x | 0.926x to 1.314x | 13 | no |
| gene:g003 | a | views | 1.118x | 0.858x to 1.392x | 19 | no |
| length | 25 to 34 s | views | 1.115x | 0.844x to 1.37x | 30 | no |

## Interactions whose interval clears no difference

18 of 94 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.056x beyond its usual effect, 90% interval 1.003x to 1.111x, 18 Shorts; q 0.328, fails the luck check
- Music: on on replies (views): 0.947x beyond its usual effect, 90% interval 0.9x to 0.997x, 11 Shorts; q 0.328, fails the luck check
- Entertainment: on on replies (views): 1.052x beyond its usual effect, 90% interval 1.008x to 1.087x, 8 Shorts; q 0.201, fails the luck check
- Entertainment: off on replies (views): 0.951x beyond its usual effect, 90% interval 0.92x to 0.992x, 9 Shorts; q 0.201, fails the luck check
- Sport: statement on hook_type (views): 0.952x beyond its usual effect, 90% interval 0.935x to 0.992x, 4 Shorts; q 0.149, fails the luck check
- Sport: number on hook_type (views): 1.05x beyond its usual effect, 90% interval 1.008x to 1.069x, 5 Shorts; q 0.149, fails the luck check
- Sport: held back on title_answer (views): 1.042x beyond its usual effect, 90% interval 1.007x to 1.064x, 3 Shorts; q 0.149, fails the luck check
- Sport: stated on title_answer (views): 0.96x beyond its usual effect, 90% interval 0.94x to 0.993x, 5 Shorts; q 0.149, fails the luck check
- Gaming: on on replies (views): 1.041x beyond its usual effect, 90% interval 1.002x to 1.091x, 19 Shorts; q 0.361, fails the luck check
- Gaming: off on replies (views): 0.961x beyond its usual effect, 90% interval 0.917x to 0.998x, 14 Shorts; q 0.361, fails the luck check
- Gaming: lab on fx_energy (views): 1.032x beyond its usual effect, 90% interval 1.008x to 1.05x, 3 Shorts; q 0.149, fails the luck check
- Gaming: held back on title_answer (views): 1.032x beyond its usual effect, 90% interval 1.004x to 1.048x, 4 Shorts; q 0.191, fails the luck check
- Gaming: steady on fx_energy (views): 0.969x beyond its usual effect, 90% interval 0.952x to 0.992x, 9 Shorts; q 0.149, fails the luck check
- Gaming: stated on title_answer (views): 0.969x beyond its usual effect, 90% interval 0.954x to 0.996x, 10 Shorts; q 0.191, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.031x beyond its usual effect, 90% interval 1.002x to 1.049x, 3 Shorts; q 0.191, fails the luck check

## Controls

- exploration Short: 0.851x (0.464x to 1.562x)
- topic heat (per point): 0.96x (0.784x to 1.202x)
