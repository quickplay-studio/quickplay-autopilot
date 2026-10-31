# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 198 Shorts, 97 columns, residual spread 1.512, effective parameters 19.7
- engaged: 182 Shorts, 84 columns, residual spread 0.333, effective parameters 41.2

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.358x | 1.077x to 1.624x | 14 | yes |
| sub_push | none | views | 1.321x | 1.044x to 1.657x | 25 | yes |
| fx_energy | lab | views | 1.224x | 0.941x to 1.504x | 22 | no |
| title_search | search phrase | views | 1.168x | 0.879x to 1.578x | 35 | no |
| length | 25 to 34 s | views | 1.162x | 0.871x to 1.525x | 30 | no |
| franchise | named | views | 1.159x | 0.911x to 1.483x | 20 | no |
| gene:g004 | b | engaged | 1.148x | 0.842x to 1.452x | 3 | no |
| replies | on | views | 1.122x | 0.914x to 1.463x | 89 | no |
| fx_grade | natural | views | 1.119x | 0.865x to 1.374x | 19 | no |
| fx_slot | 06:00 to 12:00 | views | 1.107x | 0.833x to 1.382x | 27 | no |
| title_emoji | none | views | 1.105x | 0.881x to 1.436x | 38 | no |
| fx_opening | lab | engaged | 1.094x | 0.767x to 1.479x | 11 | no |

## Interactions whose interval clears no difference

16 of 112 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.055x beyond its usual effect, 90% interval 1.001x to 1.097x, 9 Shorts; q 0.331, fails the luck check
- Entertainment: off on replies (views): 0.948x beyond its usual effect, 90% interval 0.912x to 0.999x, 10 Shorts; q 0.331, fails the luck check
- Sport: number on hook_type (views): 1.044x beyond its usual effect, 90% interval 1.004x to 1.067x, 8 Shorts; q 0.158, fails the luck check
- Sport: statement on hook_type (views): 0.958x beyond its usual effect, 90% interval 0.937x to 0.996x, 7 Shorts; q 0.158, fails the luck check
- Sport: plain on franchise (views): 1.039x beyond its usual effect, 90% interval 1.006x to 1.057x, 6 Shorts; q 0.158, fails the luck check
- Sport: named on franchise (views): 0.963x beyond its usual effect, 90% interval 0.946x to 0.994x, 4 Shorts; q 0.158, fails the luck check
- Gaming: steady on fx_energy (views): 0.964x beyond its usual effect, 90% interval 0.946x to 0.99x, 9 Shorts; q 0.158, fails the luck check
- Gaming: lab on fx_energy (views): 1.037x beyond its usual effect, 90% interval 1.01x to 1.058x, 4 Shorts; q 0.158, fails the luck check
- Sport: a on gene:g003 (views): 1.037x beyond its usual effect, 90% interval 1.006x to 1.062x, 5 Shorts; q 0.231, fails the luck check
- Sport: b on gene:g003 (views): 0.965x beyond its usual effect, 90% interval 0.942x to 0.994x, 6 Shorts; q 0.231, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.036x beyond its usual effect, 90% interval 1.008x to 1.054x, 3 Shorts; q 0.158, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.949x to 0.992x, 6 Shorts; q 0.158, fails the luck check
- Sport: search phrase on title_search (views): 0.966x beyond its usual effect, 90% interval 0.948x to 0.996x, 10 Shorts; q 0.218, fails the luck check
- Sport: curiosity on title_search (views): 1.035x beyond its usual effect, 90% interval 1.004x to 1.055x, 4 Shorts; q 0.218, fails the luck check
- Entertainment: held back on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.949x to 0.991x, 7 Shorts; q 0.158, fails the luck check

## Controls

- exploration Short: 0.763x (0.36x to 1.55x)
- topic heat (per point): 0.962x (0.792x to 1.197x)
