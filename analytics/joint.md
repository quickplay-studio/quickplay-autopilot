# The joint model (every test factor at once)

Updated 2026-10-30. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 191 Shorts, 95 columns, residual spread 1.554, effective parameters 18.6
- engaged: 172 Shorts, 66 columns, residual spread 0.301, effective parameters 37.3

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.296x | 0.994x to 1.504x | 12 | no |
| fx_opening | image_first | engaged | 1.256x | 0.965x to 1.641x | 7 | no |
| fx_energy | lab | views | 1.23x | 0.899x to 1.495x | 18 | no |
| sub_push | none | views | 1.206x | 0.947x to 1.486x | 22 | no |
| fx_slot | 06:00 to 12:00 | views | 1.204x | 0.921x to 1.524x | 23 | no |
| fx_grade | natural | views | 1.17x | 0.899x to 1.442x | 17 | no |
| franchise | named | views | 1.143x | 0.882x to 1.416x | 19 | no |
| replies | on | views | 1.143x | 0.874x to 1.502x | 82 | no |
| title_answer | held back | views | 1.141x | 0.885x to 1.432x | 23 | no |
| writer_arm | gemini flash | views | 1.138x | 0.98x to 1.289x | 7 | no |
| title_emoji | none | views | 1.133x | 0.919x to 1.454x | 33 | no |
| length | 25 to 34 s | views | 1.125x | 0.866x to 1.413x | 31 | no |

## Interactions whose interval clears no difference

16 of 102 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Music: off on replies (views): 1.055x beyond its usual effect, 90% interval 1.003x to 1.112x, 18 Shorts; q 0.371, fails the luck check
- Music: on on replies (views): 0.948x beyond its usual effect, 90% interval 0.899x to 0.997x, 11 Shorts; q 0.371, fails the luck check
- Entertainment: off on replies (views): 0.949x beyond its usual effect, 90% interval 0.915x to 0.995x, 9 Shorts; q 0.294, fails the luck check
- Entertainment: on on replies (views): 1.053x beyond its usual effect, 90% interval 1.005x to 1.093x, 10 Shorts; q 0.294, fails the luck check
- Sport: statement on hook_type (views): 0.954x beyond its usual effect, 90% interval 0.935x to 0.99x, 4 Shorts; q 0.279, fails the luck check
- Sport: number on hook_type (views): 1.048x beyond its usual effect, 90% interval 1.01x to 1.07x, 6 Shorts; q 0.279, fails the luck check
- Sport: stated on title_answer (views): 0.963x beyond its usual effect, 90% interval 0.947x to 0.996x, 5 Shorts; q 0.279, fails the luck check
- Sport: held back on title_answer (views): 1.038x beyond its usual effect, 90% interval 1.004x to 1.056x, 4 Shorts; q 0.279, fails the luck check
- Gaming: stated on title_answer (views): 0.967x beyond its usual effect, 90% interval 0.946x to 0.997x, 9 Shorts; q 0.279, fails the luck check
- Gaming: held back on title_answer (views): 1.034x beyond its usual effect, 90% interval 1.003x to 1.057x, 4 Shorts; q 0.279, fails the luck check
- Gaming: lab on fx_energy (views): 1.033x beyond its usual effect, 90% interval 1.005x to 1.046x, 4 Shorts; q 0.279, fails the luck check
- Gaming: steady on fx_energy (views): 0.969x beyond its usual effect, 90% interval 0.956x to 0.995x, 8 Shorts; q 0.279, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.03x beyond its usual effect, 90% interval 1.004x to 1.05x, 3 Shorts; q 0.294, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.971x beyond its usual effect, 90% interval 0.952x to 0.996x, 6 Shorts; q 0.294, fails the luck check
- Entertainment: shown on angles (views): 0.976x beyond its usual effect, 90% interval 0.962x to 0.996x, 5 Shorts; q 0.279, fails the luck check

## Controls

- exploration Short: 0.79x (0.416x to 1.693x)
- topic heat (per point): 0.929x (0.75x to 1.162x)
