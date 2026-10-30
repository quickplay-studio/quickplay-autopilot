# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 191 Shorts, 94 columns, residual spread 1.564, effective parameters 18.6
- engaged: 184 Shorts, 87 columns, residual spread 0.332, effective parameters 42.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.311x | 1.027x to 1.507x | 13 | yes |
| gene:g004 | b | engaged | 1.265x | 0.91x to 1.588x | 5 | no |
| fx_grade | natural | views | 1.213x | 0.948x to 1.494x | 17 | no |
| sub_push | none | views | 1.179x | 0.911x to 1.422x | 23 | no |
| title_emoji | none | views | 1.164x | 0.863x to 1.47x | 35 | no |
| fx_energy | lab | views | 1.152x | 0.896x to 1.419x | 18 | no |
| fx_slot | 06:00 to 12:00 | views | 1.139x | 0.871x to 1.504x | 24 | no |
| franchise | named | views | 1.133x | 0.88x to 1.438x | 19 | no |
| replies | on | views | 1.13x | 0.853x to 1.425x | 84 | no |
| writer_arm | gemini flash | views | 1.124x | 0.988x to 1.252x | 8 | no |
| length | 25 to 34 s | views | 1.119x | 0.842x to 1.432x | 31 | no |
| ending | loop | views | 1.086x | 0.859x to 1.354x | 33 | no |

## Interactions whose interval clears no difference

14 of 106 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.052x beyond its usual effect, 90% interval 1.011x to 1.091x, 10 Shorts; q 0.229, fails the luck check
- Entertainment: off on replies (views): 0.951x beyond its usual effect, 90% interval 0.917x to 0.989x, 9 Shorts; q 0.229, fails the luck check
- Sport: statement on hook_type (views): 0.956x beyond its usual effect, 90% interval 0.939x to 0.992x, 4 Shorts; q 0.192, fails the luck check
- Sport: number on hook_type (views): 1.046x beyond its usual effect, 90% interval 1.008x to 1.064x, 6 Shorts; q 0.192, fails the luck check
- Sport: stated on title_answer (views): 0.964x beyond its usual effect, 90% interval 0.947x to 0.995x, 5 Shorts; q 0.215, fails the luck check
- Sport: held back on title_answer (views): 1.037x beyond its usual effect, 90% interval 1.005x to 1.056x, 4 Shorts; q 0.215, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.967x beyond its usual effect, 90% interval 0.949x to 0.995x, 6 Shorts; q 0.192, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.034x beyond its usual effect, 90% interval 1.005x to 1.054x, 3 Shorts; q 0.192, fails the luck check
- Gaming: stated on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.949x to 0.999x, 10 Shorts; q 0.229, fails the luck check
- Gaming: held back on title_answer (views): 1.033x beyond its usual effect, 90% interval 1.001x to 1.054x, 4 Shorts; q 0.229, fails the luck check
- Gaming: lab on fx_energy (views): 1.032x beyond its usual effect, 90% interval 1.006x to 1.049x, 4 Shorts; q 0.192, fails the luck check
- Gaming: steady on fx_energy (views): 0.969x beyond its usual effect, 90% interval 0.953x to 0.994x, 9 Shorts; q 0.192, fails the luck check
- Entertainment: hidden on angles (views): 1.028x beyond its usual effect, 90% interval 1.007x to 1.044x, 3 Shorts; q 0.192, fails the luck check
- Entertainment: shown on angles (views): 0.973x beyond its usual effect, 90% interval 0.958x to 0.993x, 5 Shorts; q 0.192, fails the luck check

## Controls

- exploration Short: 0.948x (0.492x to 1.721x)
- topic heat (per point): 0.949x (0.773x to 1.177x)
