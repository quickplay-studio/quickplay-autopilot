# Sameness (does the channel look interchangeable?)

Updated 2026-10-28. YouTube's inauthentic-content policy refuses monetisation to channels whose videos feel interchangeable or template-made. Score: mean pairwise similarity (0 to 1) of a channel's Shorts over 14 days (pipeline/sameness.py: narration, title pattern, opening, look, format and series). The writer rewrites, then drops, a draft over 0.3 against any recent Short, and picks another format when one recipe holds 35% of the window. An issue opens when a channel's score is over 0.2 two days running.

- clips: score 0.0986 on 2026-10-28 over 9 boards (alert at 0.2); commonest recipe 22% of the window: format one_detail, hook statement, look standard+lab-captions-1019, series Match Day.
  - most alike this week: QD-224 "Match Day #2: Mitchell Lawrie faces Luke Littler on Netflix " and QD-199 "Match Day #1: Why do cats purr" (0.18)
  - most alike this week: QD-261 "Match Day #4: Harry Kane Ballon d'Or: the historic detail 🏆" and QD-232 "Match Day #3: Harry Kane wins Ballon d'Or 2026 ⚽" (0.18)
- gaming: score 0.1166 on 2026-10-28 over 6 boards (alert at 0.2); commonest recipe 17% of the window: format countdown, hook twist, look standard+lab-captions-1024, series Game Lore.
  - most alike this week: QD-257 "Level Up #3: GTA 6 Union Vote: Rockstar's historic moment ⚙️" and QD-196 "Level Up #1: Minecraft: 400 million copies sold 🎮" (0.20)
  - most alike this week: QD-230 "Game Lore #3: GTA 6: the massive storage size revealed" and QD-204 "Game Lore #2: Sonic the Hedgehog free RPGs 🎲" (0.17)
- irl: score 0.14 on 2026-10-28 over 9 boards (alert at 0.2); commonest recipe 22% of the window: format one_detail, hook number, look minimal+low, series Did You Know.
  - most alike this week: QD-258 "Did You Know #6: Walter Koenig: Star Trek actor dies aged 90" and QD-222 "Did You Know #4: Walter Koenig: the Star Trek legend's final" (0.21)
  - most alike this week: QD-260 "Did You Know: Walter Koenig tribute: George Takei's touching" and QD-258 "Did You Know #6: Walter Koenig: Star Trek actor dies aged 90" (0.21)
- main: score 0.0634 on 2026-10-28 over 178 boards (alert at 0.2); commonest recipe 4% of the window: format one_detail, hook statement, look clean.
  - most alike this week: QD-255 "Star Stories #7: Walter Koenig: the audition secret you neve" and QD-253 "Walter Koenig: the audition secret you missed 🖖" (0.35)
  - most alike this week: QD-108 "Morgan Wallen and Ella Langley duet details 🎶" and QD-101 "Ella Langley and Morgan Wallen released new duet 🎶" (0.32)
