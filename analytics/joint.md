# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 194 Shorts, 99 columns, residual spread 1.548, effective parameters 19.2
- engaged: 183 Shorts, 88 columns, residual spread 0.319, effective parameters 42.8

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.303x | 1.014x to 1.55x | 13 | yes |
| gene:g004 | b | engaged | 1.266x | 0.962x to 1.583x | 5 | no |
| sub_push | none | views | 1.258x | 0.994x to 1.554x | 24 | no |
| fx_grade | natural | views | 1.245x | 0.999x to 1.51x | 17 | no |
| fx_energy | lab | views | 1.206x | 0.964x to 1.506x | 21 | no |
| fx_slot | 06:00 to 12:00 | views | 1.168x | 0.889x to 1.474x | 26 | no |
| title_emoji | none | views | 1.146x | 0.887x to 1.45x | 37 | no |
| franchise | named | views | 1.145x | 0.878x to 1.381x | 22 | no |
| length | 25 to 34 s | views | 1.138x | 0.828x to 1.391x | 31 | no |
| writer_arm | gemini flash | views | 1.133x | 0.994x to 1.257x | 8 | no |
| fx_opening | lab | engaged | 1.113x | 0.785x to 1.386x | 10 | no |
| replies | on | views | 1.102x | 0.85x to 1.423x | 86 | no |

## Interactions whose interval clears no difference

26 of 116 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.053x beyond its usual effect, 90% interval 1.009x to 1.095x, 10 Shorts; q 0.203, fails the luck check
- Entertainment: off on replies (views): 0.95x beyond its usual effect, 90% interval 0.913x to 0.991x, 9 Shorts; q 0.203, fails the luck check
- Music: on on replies (views): 0.95x beyond its usual effect, 90% interval 0.908x to 0.999x, 11 Shorts; q 0.326, fails the luck check
- Music: off on replies (views): 1.052x beyond its usual effect, 90% interval 1.001x to 1.102x, 18 Shorts; q 0.326, fails the luck check
- Sport: number on hook_type (views): 1.044x beyond its usual effect, 90% interval 1.007x to 1.066x, 6 Shorts; q 0.132, fails the luck check
- Sport: statement on hook_type (views): 0.958x beyond its usual effect, 90% interval 0.938x to 0.993x, 7 Shorts; q 0.132, fails the luck check
- Film: 12:00 to 18:00 on fx_slot (views): 0.96x beyond its usual effect, 90% interval 0.932x to 0.999x, 7 Shorts; q 0.203, fails the luck check
- Film: 06:00 to 12:00 on fx_slot (views): 1.041x beyond its usual effect, 90% interval 1.001x to 1.072x, 3 Shorts; q 0.203, fails the luck check
- Gaming: steady on fx_energy (views): 0.965x beyond its usual effect, 90% interval 0.95x to 0.99x, 8 Shorts; q 0.132, fails the luck check
- Gaming: lab on fx_energy (views): 1.036x beyond its usual effect, 90% interval 1.01x to 1.053x, 4 Shorts; q 0.132, fails the luck check
- Sport: plain on franchise (views): 1.036x beyond its usual effect, 90% interval 1.008x to 1.052x, 4 Shorts; q 0.132, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.948x to 0.991x, 6 Shorts; q 0.132, fails the luck check
- Sport: named on franchise (views): 0.966x beyond its usual effect, 90% interval 0.95x to 0.992x, 4 Shorts; q 0.132, fails the luck check
- Sport: b on gene:g003 (views): 0.966x beyond its usual effect, 90% interval 0.947x to 0.997x, 4 Shorts; q 0.145, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.009x to 1.055x, 3 Shorts; q 0.132, fails the luck check

## Controls

- exploration Short: 0.964x (0.539x to 1.942x)
- topic heat (per point): 0.935x (0.772x to 1.104x)
