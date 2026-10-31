# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 197 Shorts, 97 columns, residual spread 1.516, effective parameters 19.6
- engaged: 182 Shorts, 84 columns, residual spread 0.333, effective parameters 41.2

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.374x | 1.068x to 1.606x | 14 | yes |
| sub_push | none | views | 1.325x | 1.027x to 1.597x | 25 | yes |
| fx_energy | lab | views | 1.213x | 0.928x to 1.455x | 22 | no |
| length | 25 to 34 s | views | 1.169x | 0.897x to 1.477x | 30 | no |
| title_search | search phrase | views | 1.152x | 0.895x to 1.455x | 35 | no |
| gene:g004 | b | engaged | 1.148x | 0.842x to 1.452x | 3 | no |
| franchise | named | views | 1.139x | 0.898x to 1.493x | 20 | no |
| replies | on | views | 1.125x | 0.877x to 1.525x | 88 | no |
| title_emoji | none | views | 1.121x | 0.909x to 1.394x | 37 | no |
| fx_grade | natural | views | 1.119x | 0.876x to 1.365x | 19 | no |
| fx_slot | 06:00 to 12:00 | views | 1.105x | 0.869x to 1.386x | 27 | no |
| gene:g004 | a | views | 1.103x | 0.924x to 1.287x | 20 | no |

## Interactions whose interval clears no difference

16 of 112 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.056x beyond its usual effect, 90% interval 1.003x to 1.107x, 9 Shorts; q 0.348, fails the luck check
- Entertainment: off on replies (views): 0.947x beyond its usual effect, 90% interval 0.904x to 0.997x, 10 Shorts; q 0.348, fails the luck check
- Sport: number on hook_type (views): 1.044x beyond its usual effect, 90% interval 1.006x to 1.068x, 8 Shorts; q 0.19, fails the luck check
- Sport: statement on hook_type (views): 0.958x beyond its usual effect, 90% interval 0.936x to 0.994x, 7 Shorts; q 0.19, fails the luck check
- Sport: named on franchise (views): 0.96x beyond its usual effect, 90% interval 0.941x to 0.991x, 4 Shorts; q 0.162, fails the luck check
- Sport: plain on franchise (views): 1.041x beyond its usual effect, 90% interval 1.009x to 1.063x, 5 Shorts; q 0.162, fails the luck check
- Sport: b on gene:g003 (views): 0.962x beyond its usual effect, 90% interval 0.941x to 0.993x, 6 Shorts; q 0.162, fails the luck check
- Sport: a on gene:g003 (views): 1.039x beyond its usual effect, 90% interval 1.007x to 1.063x, 4 Shorts; q 0.162, fails the luck check
- Sport: search phrase on title_search (views): 0.963x beyond its usual effect, 90% interval 0.943x to 0.992x, 10 Shorts; q 0.162, fails the luck check
- Sport: curiosity on title_search (views): 1.038x beyond its usual effect, 90% interval 1.008x to 1.061x, 3 Shorts; q 0.162, fails the luck check
- Gaming: lab on fx_energy (views): 1.037x beyond its usual effect, 90% interval 1.007x to 1.056x, 4 Shorts; q 0.162, fails the luck check
- Gaming: steady on fx_energy (views): 0.965x beyond its usual effect, 90% interval 0.947x to 0.993x, 9 Shorts; q 0.162, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.947x to 0.99x, 6 Shorts; q 0.162, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.01x to 1.056x, 3 Shorts; q 0.162, fails the luck check
- Entertainment: held back on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.946x to 0.992x, 7 Shorts; q 0.162, fails the luck check

## Controls

- exploration Short: 0.809x (0.433x to 1.629x)
- topic heat (per point): 0.958x (0.783x to 1.196x)
