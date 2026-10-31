# The joint model (every test factor at once)

Updated 2026-10-31. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing instruction (source joint).

- views: 196 Shorts, 96 columns, residual spread 1.521, effective parameters 19.4
- engaged: 182 Shorts, 84 columns, residual spread 0.333, effective parameters 41.2

## Top main effects (the better arm of each factor)

| factor | arm | outcome | effect | 90% interval | Shorts | clear |
|---|---|---|---|---|---|---|
| fx_opening | lab | views | 1.379x | 1.058x to 1.645x | 14 | yes |
| sub_push | none | views | 1.336x | 1.038x to 1.61x | 24 | yes |
| fx_energy | lab | views | 1.214x | 0.943x to 1.478x | 21 | no |
| length | 25 to 34 s | views | 1.175x | 0.883x to 1.554x | 30 | no |
| gene:g004 | b | engaged | 1.148x | 0.842x to 1.452x | 3 | no |
| title_search | search phrase | views | 1.138x | 0.893x to 1.465x | 35 | no |
| franchise | named | views | 1.137x | 0.887x to 1.45x | 20 | no |
| fx_grade | natural | views | 1.129x | 0.895x to 1.407x | 18 | no |
| replies | on | views | 1.127x | 0.881x to 1.505x | 87 | no |
| title_emoji | none | views | 1.125x | 0.883x to 1.438x | 36 | no |
| fx_slot | 06:00 to 12:00 | views | 1.107x | 0.874x to 1.418x | 26 | no |
| gene:g004 | a | views | 1.096x | 0.894x to 1.274x | 20 | no |

## Interactions whose interval clears no difference

16 of 110 interaction rows. With this many cells some clear a 90% interval by luck, so only those with q at or under 0.1 (Benjamini-Hochberg) are offered to evolve.py.

- Entertainment: on on replies (views): 1.056x beyond its usual effect, 90% interval 1.006x to 1.104x, 9 Shorts; q 0.326, fails the luck check
- Entertainment: off on replies (views): 0.947x beyond its usual effect, 90% interval 0.906x to 0.994x, 10 Shorts; q 0.326, fails the luck check
- Sport: statement on hook_type (views): 0.956x beyond its usual effect, 90% interval 0.936x to 0.991x, 7 Shorts; q 0.164, fails the luck check
- Sport: number on hook_type (views): 1.046x beyond its usual effect, 90% interval 1.009x to 1.068x, 7 Shorts; q 0.164, fails the luck check
- Sport: named on franchise (views): 0.96x beyond its usual effect, 90% interval 0.94x to 0.988x, 4 Shorts; q 0.164, fails the luck check
- Sport: plain on franchise (views): 1.041x beyond its usual effect, 90% interval 1.012x to 1.064x, 5 Shorts; q 0.164, fails the luck check
- Gaming: steady on fx_energy (views): 0.964x beyond its usual effect, 90% interval 0.95x to 0.989x, 9 Shorts; q 0.164, fails the luck check
- Gaming: lab on fx_energy (views): 1.037x beyond its usual effect, 90% interval 1.011x to 1.053x, 4 Shorts; q 0.164, fails the luck check
- Sport: b on gene:g003 (views): 0.965x beyond its usual effect, 90% interval 0.948x to 0.996x, 5 Shorts; q 0.177, fails the luck check
- Sport: a on gene:g003 (views): 1.036x beyond its usual effect, 90% interval 1.004x to 1.055x, 4 Shorts; q 0.177, fails the luck check
- Entertainment: 06:00 to 12:00 on fx_slot (views): 0.966x beyond its usual effect, 90% interval 0.946x to 0.993x, 6 Shorts; q 0.166, fails the luck check
- Entertainment: 12:00 to 18:00 on fx_slot (views): 1.035x beyond its usual effect, 90% interval 1.007x to 1.058x, 3 Shorts; q 0.166, fails the luck check
- Entertainment: stated on title_answer (views): 1.032x beyond its usual effect, 90% interval 1.006x to 1.051x, 4 Shorts; q 0.166, fails the luck check
- Entertainment: held back on title_answer (views): 0.969x beyond its usual effect, 90% interval 0.951x to 0.994x, 7 Shorts; q 0.166, fails the luck check
- Gaming: held back on title_answer (views): 1.029x beyond its usual effect, 90% interval 1.001x to 1.053x, 4 Shorts; q 0.385, fails the luck check

## Controls

- exploration Short: 0.811x (0.385x to 1.689x)
- topic heat (per point): 0.957x (0.764x to 1.157x)
