# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 195 Shorts, 96 columns, residual spread 1.524, effective parameters 19.4
- engaged: 182 Shorts, 84 columns, residual spread 0.333, effective parameters 41.2

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.385x | 1.058x to 1.575x | 14 | yes |
| sub_push | none | views | 1.361x | 1.074x to 1.58x | 23 | yes |
| fx_energy | lab | views | 1.214x | 0.942x to 1.534x | 21 | no |
| length | 25 to 34 s | views | 1.182x | 0.872x to 1.496x | 30 | no |
| gene:g004 | b | engaged | 1.148x | 0.842x to 1.452x | 3 | no |
| franchise | named | views | 1.137x | 0.876x to 1.47x | 20 | no |
| title_search | search phrase | views | 1.135x | 0.83x to 1.466x | 35 | no |
| fx_grade | natural | views | 1.131x | 0.92x to 1.399x | 18 | no |
| replies | on | views | 1.118x | 0.834x to 1.486x | 87 | no |
| title_emoji | none | views | 1.112x | 0.901x to 1.423x | 36 | no |
| fx_slot | 06:00 to 12:00 | views | 1.107x | 0.831x to 1.404x | 26 | no |
| gene:g004 | a | views | 1.099x | 0.904x to 1.313x | 20 | no |

## Interactions whose interval clears no difference

20 of 110 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.055x beyond its usual effect, 90% interval 1.003x to 1.114x, 18 Shorts; q 0.402, fails the luck check
- Music: on on replies (views): 0.948x beyond its usual effect, 90% interval 0.898x to 0.997x, 11 Shorts; q 0.402, fails the luck check
- Entertainment: on on replies (views): 1.053x beyond its usual effect, 90% interval 1.002x to 1.093x, 9 Shorts; q 0.278, fails the luck check
- Entertainment: off on replies (views): 0.95x beyond its usual effect, 90% interval 0.915x to 0.998x, 9 Shorts; q 0.278, fails the luck check
- Sport: statement on hook_type (views): 0.955x beyond its usual effect, 90% interval 0.937x to 0.99x, 7 Shorts; q 0.097, passes the luck check
- Sport: number on hook_type (views): 1.047x beyond its usual effect, 90% interval 1.01x to 1.067x, 7 Shorts; q 0.097, passes the luck check
- Sport: named on franchise (views): 0.96x beyond its usual effect, 90% interval 0.945x to 0.992x, 4 Shorts; q 0.097, passes the luck check
- Sport: plain on franchise (views): 1.041x beyond its usual effect, 90% interval 1.008x to 1.058x, 5 Shorts; q 0.097, passes the luck check
- Gaming: lab on fx_energy (views): 1.038x beyond its usual effect, 90% interval 1.009x to 1.054x, 4 Shorts; q 0.097, passes the luck check
- Gaming: steady on fx_energy (views): 0.964x beyond its usual effect, 90% interval 0.948x to 0.991x, 9 Shorts; q 0.097, passes the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.948x to 0.992x, 6 Shorts; q 0.097, passes the luck check
- Entertainment: held back on title_answer (views): 0.966x beyond its usual effect, 90% interval 0.949x to 0.992x, 7 Shorts; q 0.097, passes the luck check
- Sport: b on gene:g003 (views): 0.966x beyond its usual effect, 90% interval 0.948x to 0.997x, 5 Shorts; q 0.25, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.008x to 1.055x, 3 Shorts; q 0.097, passes the luck check
- Entertainment: stated on title_answer (views): 1.035x beyond its usual effect, 90% interval 1.009x to 1.053x, 3 Shorts; q 0.097, passes the luck check

## Controls

- exploration Short: 0.811x (0.454x to 1.711x)
- topic heat (per point): 0.96x (0.777x to 1.201x)
