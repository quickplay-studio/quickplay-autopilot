# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 191 Shorts, 94 columns, residual spread 1.555, effective parameters 18.5
- engaged: 155 Shorts, 48 columns, residual spread 0.301, effective parameters 30.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.296x | 0.966x to 1.515x | 12 | no |
| fx_energy | lab | views | 1.229x | 0.947x to 1.545x | 17 | no |
| fx_grade | natural | views | 1.201x | 0.928x to 1.493x | 17 | no |
| first_frame | cover | engaged | 1.186x | 0.953x to 1.482x | 25 | no |
| sub_push | none | views | 1.181x | 0.938x to 1.477x | 23 | no |
| fx_slot | 06:00 to 12:00 | views | 1.174x | 0.871x to 1.469x | 24 | no |
| title_emoji | none | views | 1.169x | 0.883x to 1.485x | 33 | no |
| length | 25 to 34 s | views | 1.148x | 0.86x to 1.47x | 31 | no |
| writer_arm | gemini flash | views | 1.123x | 0.97x to 1.286x | 8 | no |
| franchise | named | views | 1.121x | 0.865x to 1.398x | 20 | no |
| title_answer | held back | views | 1.12x | 0.821x to 1.429x | 24 | no |
| replies | on | views | 1.119x | 0.847x to 1.42x | 82 | no |

## Interactions whose interval clears no difference

12 of 98 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.933x to 0.99x, 4 Shorts; q 0.175, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.01x to 1.072x, 6 Shorts; q 0.175, fails the luck check
- Entertainment: off on replies (views): 0.956x beyond its usual effect, 90% interval 0.922x to 0.996x, 9 Shorts; q 0.352, fails the luck check
- Entertainment: on on replies (views): 1.045x beyond its usual effect, 90% interval 1.004x to 1.084x, 9 Shorts; q 0.352, fails the luck check
- Sport: held back on title_answer (views): 1.04x beyond its usual effect, 90% interval 1.004x to 1.065x, 4 Shorts; q 0.31, fails the luck check
- Sport: stated on title_answer (views): 0.962x beyond its usual effect, 90% interval 0.939x to 0.996x, 5 Shorts; q 0.31, fails the luck check
- Gaming: steady on fx_energy (views): 0.968x beyond its usual effect, 90% interval 0.955x to 0.993x, 9 Shorts; q 0.175, fails the luck check
- Gaming: stated on title_answer (views): 0.968x beyond its usual effect, 90% interval 0.954x to 0.995x, 10 Shorts; q 0.175, fails the luck check
- Gaming: lab on fx_energy (views): 1.033x beyond its usual effect, 90% interval 1.007x to 1.047x, 3 Shorts; q 0.175, fails the luck check
- Gaming: held back on title_answer (views): 1.033x beyond its usual effect, 90% interval 1.005x to 1.048x, 4 Shorts; q 0.175, fails the luck check
- Entertainment: shown on angles (views): 0.976x beyond its usual effect, 90% interval 0.959x to 0.997x, 5 Shorts; q 0.352, fails the luck check
- Entertainment: hidden on angles (views): 1.024x beyond its usual effect, 90% interval 1.003x to 1.043x, 3 Shorts; q 0.352, fails the luck check

## Controls

- exploration Short: 0.841x (0.444x to 1.555x)
- topic heat (per point): 0.954x (0.77x to 1.153x)
