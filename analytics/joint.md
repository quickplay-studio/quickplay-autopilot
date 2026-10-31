# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 202 Shorts, 101 columns, residual spread 1.511, effective parameters 20.0
- engaged: 187 Shorts, 88 columns, residual spread 0.328, effective parameters 42.4

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_energy | lab | views | 1.296x | 0.983x to 1.603x | 22 | no |
| fx_opening | lab | views | 1.26x | 0.983x to 1.529x | 14 | no |
| gene:g004 | b | engaged | 1.258x | 0.906x to 1.552x | 5 | no |
| fx_slot | 06:00 to 12:00 | views | 1.256x | 0.956x to 1.528x | 27 | no |
| title_search | search phrase | views | 1.186x | 0.913x to 1.553x | 34 | no |
| sub_push | none | views | 1.184x | 0.91x to 1.553x | 26 | no |
| fx_grade | natural | views | 1.17x | 0.882x to 1.416x | 20 | no |
| angles | hidden | views | 1.165x | 0.944x to 1.441x | 25 | no |
| ending | loop | views | 1.125x | 0.859x to 1.442x | 34 | no |
| franchise | named | views | 1.121x | 0.869x to 1.396x | 22 | no |
| writer_arm | gemini flash | views | 1.11x | 0.972x to 1.24x | 9 | no |
| length | 25 to 34 s | views | 1.096x | 0.847x to 1.406x | 32 | no |

## Interactions whose interval clears no difference

20 of 120 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: off on replies (views): 0.945x beyond its usual effect, 90% interval 0.909x to 0.988x, 10 Shorts; q 0.285, fails the luck check
- Entertainment: on on replies (views): 1.058x beyond its usual effect, 90% interval 1.012x to 1.1x, 10 Shorts; q 0.285, fails the luck check
- Sport: none on title_emoji (views): 0.96x beyond its usual effect, 90% interval 0.942x to 0.994x, 10 Shorts; q 0.217, fails the luck check
- Sport: emoji on title_emoji (views): 1.041x beyond its usual effect, 90% interval 1.006x to 1.062x, 5 Shorts; q 0.217, fails the luck check
- Sport: plain on franchise (views): 1.038x beyond its usual effect, 90% interval 1.006x to 1.056x, 6 Shorts; q 0.177, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.964x beyond its usual effect, 90% interval 0.945x to 0.99x, 6 Shorts; q 0.177, fails the luck check
- Gaming: steady on fx_energy (views): 0.964x beyond its usual effect, 90% interval 0.948x to 0.991x, 10 Shorts; q 0.177, fails the luck check
- Sport: named on franchise (views): 0.964x beyond its usual effect, 90% interval 0.947x to 0.994x, 4 Shorts; q 0.177, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.037x beyond its usual effect, 90% interval 1.01x to 1.058x, 3 Shorts; q 0.177, fails the luck check
- Gaming: lab on fx_energy (views): 1.037x beyond its usual effect, 90% interval 1.009x to 1.055x, 4 Shorts; q 0.177, fails the luck check
- Gaming: stated on title_answer (views): 0.965x beyond its usual effect, 90% interval 0.949x to 0.995x, 10 Shorts; q 0.188, fails the luck check
- Gaming: held back on title_answer (views): 1.036x beyond its usual effect, 90% interval 1.005x to 1.054x, 4 Shorts; q 0.188, fails the luck check
- Sport: number on hook_type (views): 1.032x beyond its usual effect, 90% interval 1.002x to 1.057x, 8 Shorts; q 0.325, fails the luck check
- Sport: statement on hook_type (views): 0.969x beyond its usual effect, 90% interval 0.946x to 0.998x, 6 Shorts; q 0.325, fails the luck check
- Entertainment: hidden on angles (views): 1.031x beyond its usual effect, 90% interval 1.009x to 1.045x, 3 Shorts; q 0.177, fails the luck check

## Controls

- exploration Short: 0.858x (0.485x to 1.555x)
- topic heat (per point): 0.988x (0.798x to 1.207x)
