# Sameness (does the channel look interchangeable?)

Updated 2026-10-31. YouTube's inauthentic-content policy refuses monetisation to channels whose videos feel interchangeable or template-made. Score: mean pairwise similarity (0 to 1) of a channel's Shorts over 14 days (pipeline/sameness.py: narration, title pattern, opening, look, format and series). The writer rewrites, then drops, a draft over 0.3 against any recent Short, and picks another format when one recipe holds 35% of the window. An issue opens when a channel's score is over 0.2 two days running.

- clips: score 0.1174 on 2026-10-31 over 11 boards (alert at 0.2); commonest recipe 18% of the window: format one_detail, hook statement, look standard+lab-captions-1019, series Match Day.
  - most alike this week: QD-269 "Match Day #6: Caroline Weir Ballon d'Or: rank 25 revealed ⚽" and QD-268 "Match Day #5: Caroline Weir Ballon d'Or: the elite rank 🏆" (0.39)
  - most alike this week: QD-268 "Match Day #5: Caroline Weir Ballon d'Or: the elite rank 🏆" and QD-261 "Match Day #4: Harry Kane Ballon d'Or: the historic detail 🏆" (0.26)
- gaming: score 0.1024 on 2026-10-31 over 9 boards (alert at 0.2); commonest recipe 11% of the window: format countdown, hook twist, look standard+lab-captions-1024, series Game Lore.
  - most alike this week: QD-267 "Player One #1: Minecraft: 400 million copies sold" and QD-196 "Level Up #1: Minecraft: 400 million copies sold 🎮" (0.35)
  - most alike this week: QD-315 "Game Lore #4: GTA 6 launches on 19 November 2026 with a twis" and QD-230 "Game Lore #3: GTA 6: the massive storage size revealed" (0.21)
- irl: score 0.1323 on 2026-10-31 over 14 boards (alert at 0.2); commonest recipe 21% of the window: format one_detail, hook number, look minimal+low, series Did You Know.
  - most alike this week: QD-319 "Did You Know #12: Patrick Stewart: the secret to his success" and QD-318 "Did You Know #11: Patrick Stewart was knighted in 2010" (0.32)
  - most alike this week: QD-317 "Did You Know #10: Sir Patrick Stewart: the detail you missed" and QD-222 "Did You Know #4: Walter Koenig: the Star Trek legend's final" (0.27)
- main: score 0.0631 on 2026-10-31 over 218 boards (alert at 0.2); commonest recipe 4% of the window: format one_detail, hook statement, look clean.
  - most alike this week: QD-255 "Star Stories #7: Walter Koenig: the audition secret you neve" and QD-253 "Walter Koenig: the audition secret you missed 🖖" (0.35)
  - most alike this week: QD-209 "GTA 6 hits consoles on 19 November 🎮" and QD-195 "Game Facts #3: GTA 6 is arriving on 19 November 2026" (0.30)
