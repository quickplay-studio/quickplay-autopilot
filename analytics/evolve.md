# The self-evolving round

Updated 2026-10-26. pipeline/evolve.py runs daily (evolve.yml): it retires settled contests, keeps winners as champions, opens new contests from four sources, adopts winning writing instructions (genes) into the recipe and prunes them. Settings: config.json evolve.

## Live round (13 of 13)

| factor | arms | origin | started |
|---|---|---|---|
| angles | shown vs hidden | round 1 | 2026-10-25 |
| ending | loop vs question | round 1 | 2026-10-25 |
| first_frame | cover vs photo | round 1 | 2026-10-25 |
| franchise | named vs plain | round 1 | 2026-10-25 |
| fx_energy | steady vs lab | round 1 | 2026-10-25 |
| fx_grade | natural vs lab | round 1 | 2026-10-25 |
| fx_opening | image_first vs lab | round 1 | 2026-10-25 |
| fx_slot | 06:00 to 12:00 vs 12:00 to 18:00 | round 1 | 2026-10-25 |
| writing instruction g001: Famous name as first words | a vs b | gene | 2026-10-26 |
| hook_type | statement vs number | round 1 | 2026-10-25 |
| length | 25 to 34 s vs 35 to 44 s | round 1 | 2026-10-25 |
| title_search | search phrase vs curiosity | round 1 | 2026-10-25 |
| writing instruction g002: Headline number in sentence one | a vs b | gene | 2026-10-26 |

## Champions

- none yet

## Adopted genes (0 of at most 6)

- none yet

## Genes under test

- g001 (new): Famous name as first words
- g002 (new): Headline number in sentence one

Rejected so far: 0. Retired: 0.

## Where contests come from

| source | contests settled | wins | win rate |
|---|---|---|---|
| neighbour | 0 | 0 | no contests yet |
| retest | 0 | 0 | no contests yet |
| gene | 0 | 0 | no contests yet |
| mutate | 0 | 0 | no contests yet |

A win is a challenger (arm b, the new arm) that beat the incumbent.

## Last 10 log lines

- 2026-10-26 bootstrap     round copied from config test_round (11 factors)
- 2026-10-26 open gene:g001 a vs b gene  Famous name as first words: Open with the full name of the best-known person, band, game or brand in the fact pack as the very first words of the script, before any number, question or setup. (by claude:opus)
- 2026-10-26 open gene:g002 a vs b gene  Headline number in sentence one: Put the single most striking number from the fact pack (a time, size, age, rank or count) in the first sentence, attached to what it measures. (by claude:opus)
