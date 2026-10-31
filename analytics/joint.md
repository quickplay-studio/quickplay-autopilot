# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 198 Shorts, 99 columns, residual spread 1.539, effective parameters 19.3
- engaged: 186 Shorts, 88 columns, residual spread 0.329, effective parameters 42.1

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| gene:g004 | b | engaged | 1.305x | 0.931x to 1.624x | 4 | no |
| fx_opening | lab | views | 1.285x | 1.035x to 1.51x | 14 | yes |
| sub_push | none | views | 1.254x | 0.98x to 1.538x | 23 | no |
| fx_grade | natural | views | 1.242x | 0.981x to 1.51x | 18 | no |
| fx_energy | lab | views | 1.202x | 0.896x to 1.54x | 22 | no |
| length | 25 to 34 s | views | 1.156x | 0.909x to 1.558x | 31 | no |
| fx_slot | 06:00 to 12:00 | views | 1.152x | 0.865x to 1.415x | 27 | no |
| franchise | named | views | 1.136x | 0.891x to 1.371x | 21 | no |
| title_emoji | none | views | 1.135x | 0.87x to 1.424x | 37 | no |
| writer_arm | gemini flash | views | 1.129x | 0.975x to 1.245x | 8 | no |
| ending | loop | views | 1.11x | 0.842x to 1.448x | 34 | no |
| replies | on | views | 1.097x | 0.853x to 1.467x | 87 | no |

## Interactions whose interval clears no difference

20 of 116 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.055x beyond its usual effect, 90% interval 1.01x to 1.091x, 10 Shorts; q 0.201, fails the luck check
- Entertainment: off on replies (views): 0.948x beyond its usual effect, 90% interval 0.916x to 0.99x, 9 Shorts; q 0.201, fails the luck check
- Sport: statement on hook_type (views): 0.955x beyond its usual effect, 90% interval 0.935x to 0.992x, 7 Shorts; q 0.165, fails the luck check
- Sport: number on hook_type (views): 1.047x beyond its usual effect, 90% interval 1.008x to 1.07x, 7 Shorts; q 0.165, fails the luck check
- Sport: named on franchise (views): 0.963x beyond its usual effect, 90% interval 0.947x to 0.993x, 4 Shorts; q 0.165, fails the luck check
- Sport: plain on franchise (views): 1.038x beyond its usual effect, 90% interval 1.007x to 1.056x, 5 Shorts; q 0.165, fails the luck check
- Music: photo on first_frame (views): 0.964x beyond its usual effect, 90% interval 0.934x to 0.998x, 5 Shorts; q 0.306, fails the luck check
- Music: cover on first_frame (views): 1.037x beyond its usual effect, 90% interval 1.002x to 1.071x, 4 Shorts; q 0.306, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.953x to 0.99x, 6 Shorts; q 0.165, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.01x to 1.05x, 3 Shorts; q 0.165, fails the luck check
- Film: curiosity on title_search (views): 0.967x beyond its usual effect, 90% interval 0.941x to 0.999x, 7 Shorts; q 0.306, fails the luck check
- Film: search phrase on title_search (views): 1.034x beyond its usual effect, 90% interval 1.001x to 1.063x, 4 Shorts; q 0.306, fails the luck check
- Sport: b on gene:g003 (views): 0.968x beyond its usual effect, 90% interval 0.948x to 0.999x, 5 Shorts; q 0.235, fails the luck check
- Sport: a on gene:g003 (views): 1.033x beyond its usual effect, 90% interval 1.001x to 1.054x, 4 Shorts; q 0.235, fails the luck check
- Entertainment: stated on title_answer (views): 1.03x beyond its usual effect, 90% interval 1.005x to 1.049x, 3 Shorts; q 0.201, fails the luck check

## Controls

- exploration Short: 0.92x (0.472x to 1.798x)
- topic heat (per point): 0.937x (0.735x to 1.148x)
