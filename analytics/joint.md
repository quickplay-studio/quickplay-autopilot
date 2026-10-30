# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 190 Shorts, 94 columns, residual spread 1.545, effective parameters 18.5
- engaged: 172 Shorts, 67 columns, residual spread 0.308, effective parameters 37.0

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.295x | 0.974x to 1.55x | 12 | no |
| fx_energy | lab | views | 1.235x | 0.986x to 1.535x | 17 | no |
| title_emoji | none | views | 1.229x | 0.966x to 1.546x | 32 | no |
| fx_grade | natural | views | 1.196x | 0.937x to 1.52x | 17 | no |
| fx_opening | image_first | engaged | 1.179x | 0.943x to 1.524x | 7 | no |
| hook_type | number | views | 1.167x | 0.912x to 1.466x | 32 | no |
| fx_slot | 06:00 to 12:00 | views | 1.166x | 0.874x to 1.479x | 24 | no |
| sub_push | none | views | 1.154x | 0.902x to 1.438x | 23 | no |
| replies | on | views | 1.153x | 0.852x to 1.504x | 81 | no |
| length | 25 to 34 s | views | 1.137x | 0.838x to 1.427x | 30 | no |
| writer_arm | gemini flash | views | 1.133x | 0.992x to 1.255x | 8 | no |
| first_frame | cover | engaged | 1.116x | 0.931x to 1.385x | 34 | no |

## Interactions whose interval clears no difference

16 of 100 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Film: photo on first_frame (engaged): 1.092x beyond its usual effect, 90% interval 1.001x to 1.193x, 7 Shorts; q 0.309, fails the luck check
- Film: cover on first_frame (engaged): 0.916x beyond its usual effect, 90% interval 0.838x to 0.999x, 5 Shorts; q 0.309, fails the luck check
- Music: off on replies (views): 1.062x beyond its usual effect, 90% interval 1.002x to 1.118x, 18 Shorts; q 0.318, fails the luck check
- Music: on on replies (views): 0.942x beyond its usual effect, 90% interval 0.894x to 0.998x, 11 Shorts; q 0.318, fails the luck check
- Entertainment: off on replies (views): 0.949x beyond its usual effect, 90% interval 0.913x to 0.994x, 9 Shorts; q 0.318, fails the luck check
- Entertainment: on on replies (views): 1.053x beyond its usual effect, 90% interval 1.006x to 1.096x, 10 Shorts; q 0.318, fails the luck check
- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.93x to 0.989x, 4 Shorts; q 0.277, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.011x to 1.076x, 6 Shorts; q 0.277, fails the luck check
- Sport: held back on title_answer (views): 1.04x beyond its usual effect, 90% interval 1.008x to 1.062x, 4 Shorts; q 0.291, fails the luck check
- Sport: stated on title_answer (views): 0.962x beyond its usual effect, 90% interval 0.941x to 0.992x, 5 Shorts; q 0.291, fails the luck check
- Gaming: steady on fx_energy (views): 0.967x beyond its usual effect, 90% interval 0.952x to 0.993x, 9 Shorts; q 0.277, fails the luck check
- Gaming: lab on fx_energy (views): 1.034x beyond its usual effect, 90% interval 1.007x to 1.051x, 3 Shorts; q 0.277, fails the luck check
- Gaming: held back on title_answer (views): 1.027x beyond its usual effect, 90% interval 1.001x to 1.045x, 4 Shorts; q 0.318, fails the luck check
- Gaming: stated on title_answer (views): 0.974x beyond its usual effect, 90% interval 0.957x to 0.999x, 9 Shorts; q 0.318, fails the luck check
- Entertainment: shown on angles (views): 0.978x beyond its usual effect, 90% interval 0.964x to 0.999x, 5 Shorts; q 0.318, fails the luck check

## Controls

- exploration Short: 1.235x (0.658x to 2.076x)
- topic heat (per point): 0.917x (0.747x to 1.118x)
