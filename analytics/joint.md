# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 193 Shorts, 99 columns, residual spread 1.547, effective parameters 19.1
- engaged: 183 Shorts, 88 columns, residual spread 0.319, effective parameters 42.8

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.271x | 1.013x to 1.492x | 13 | yes |
| gene:g004 | b | engaged | 1.266x | 0.962x to 1.583x | 5 | no |
| sub_push | none | views | 1.209x | 0.966x to 1.47x | 24 | no |
| fx_grade | natural | views | 1.208x | 0.947x to 1.514x | 17 | no |
| title_emoji | none | views | 1.183x | 0.936x to 1.486x | 36 | no |
| fx_energy | lab | views | 1.143x | 0.897x to 1.427x | 21 | no |
| franchise | named | views | 1.135x | 0.876x to 1.428x | 22 | no |
| writer_arm | gemini flash | views | 1.134x | 1.004x to 1.25x | 8 | yes |
| fx_slot | 06:00 to 12:00 | views | 1.131x | 0.87x to 1.435x | 26 | no |
| replies | on | views | 1.124x | 0.869x to 1.464x | 85 | no |
| fx_opening | lab | engaged | 1.113x | 0.785x to 1.386x | 10 | no |
| length | 25 to 34 s | views | 1.107x | 0.858x to 1.415x | 31 | no |

## Interactions whose interval clears no difference

22 of 116 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.053x beyond its usual effect, 90% interval 1.005x to 1.093x, 10 Shorts; q 0.219, fails the luck check
- Entertainment: off on replies (views): 0.95x beyond its usual effect, 90% interval 0.915x to 0.995x, 9 Shorts; q 0.219, fails the luck check
- Sport: statement on hook_type (views): 0.956x beyond its usual effect, 90% interval 0.936x to 0.987x, 7 Shorts; q 0.124, fails the luck check
- Sport: number on hook_type (views): 1.046x beyond its usual effect, 90% interval 1.013x to 1.069x, 6 Shorts; q 0.124, fails the luck check
- Gaming: steady on fx_energy (views): 0.965x beyond its usual effect, 90% interval 0.949x to 0.991x, 8 Shorts; q 0.124, fails the luck check
- Gaming: stated on title_answer (views): 0.965x beyond its usual effect, 90% interval 0.949x to 0.992x, 9 Shorts; q 0.124, fails the luck check
- Sport: named on franchise (views): 0.965x beyond its usual effect, 90% interval 0.948x to 0.992x, 4 Shorts; q 0.124, fails the luck check
- Gaming: lab on fx_energy (views): 1.036x beyond its usual effect, 90% interval 1.009x to 1.054x, 4 Shorts; q 0.124, fails the luck check
- Gaming: held back on title_answer (views): 1.036x beyond its usual effect, 90% interval 1.008x to 1.054x, 4 Shorts; q 0.124, fails the luck check
- Sport: plain on franchise (views): 1.036x beyond its usual effect, 90% interval 1.008x to 1.054x, 4 Shorts; q 0.124, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.951x to 0.991x, 6 Shorts; q 0.124, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.009x to 1.052x, 3 Shorts; q 0.124, fails the luck check
- Sport: b on gene:g003 (views): 0.968x beyond its usual effect, 90% interval 0.947x to 0.993x, 4 Shorts; q 0.164, fails the luck check
- Sport: a on gene:g003 (views): 1.033x beyond its usual effect, 90% interval 1.007x to 1.056x, 4 Shorts; q 0.164, fails the luck check
- Sport: held back on title_answer (views): 1.032x beyond its usual effect, 90% interval 1.004x to 1.063x, 5 Shorts; q 0.265, fails the luck check

## Controls

- exploration Short: 0.975x (0.562x to 2.086x)
- topic heat (per point): 0.936x (0.751x to 1.129x)
