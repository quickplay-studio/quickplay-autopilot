# Quickplay handover (Monday 26 October 2026, 15:45 UK)

> The short version. The full handover (state table, channels, the learning model, open items, rules) is handover.md at
> the repo root.

Read CLAUDE.md, then run `python pipeline/digest.py`. Everything runs on GitHub; a Claude session is only for changes Charlie
asks for. Hub: https://quickplay-studio.github.io/quickplay-autopilot/hub.html

## State
- 16 of 1,000 subscribers; 7,789 of 10M Shorts views (90 days). Volume test 15 a day on main, judged from 8 November
  (status/volume.json).
- Four channels write original Shorts (main 15 a day, gaming, irl, clips 6 each); clipping paused (config clips_paused).
  The first all-channel write ran 26 October afternoon: QD-191 to QD-194 uploaded to their own channels. QD-191 (films on
  gaming) and QD-193 (games on irl) were off their lanes; CH-095 stops that from the next run.
- Music and Spanish channels wait on Charlie creating them (issues #42, #43). Facebook 1-a-day probe (#34), TikTok off (#35).

## Built 26 October (this session)
- **CH-093 watchdog** (pipeline/watchdog.py, watchdog.yml hourly at :41): GitHub dropped the 12:47 UTC trends run that day.
  The watchdog starts trends when a main slot (08:10, 12:47, 18:23 UTC) has no run 50 minutes on, and render, analytics,
  social, engage or evolve past their gap. publish.yml is left out (a dispatch defaults to "approve all"). Read only.
- **CH-094 self-evolving round** (pipeline/evolve.py, evolve.yml daily 07:23 UTC; state analytics/evolve.json, log
  evolve_log.csv, summary evolve.md). It retires settled contests (a winner becomes a champion), and opens up to 3 new
  contests a day, up to width 13, from four sources picked by Thompson sampling on their own win record:
  - neighbour: an untried arm against the champion;
  - retest: after 28 days;
  - gene: a writing instruction, tested against none;
  - mutate: a refinement of an adopted gene, against its parent.

  Genes are proposed by Claude Opus (one call a run, the free models only as fallback). Charlie, 26 October: complex steps
  on Claude, day to day on free models. Proposals must work alongside every arm under test. g001 and g002 restated the hook
  test and were retired unused; g003 (compare the first number to something familiar) is live. Off: config evolve.on false.
- **CH-095 channel lanes:** writer.evergreen_packs(lane=brief) tells the plan the channel's lane and drops ideas outside
  its categories.
- Failed boards retired: QD-126 expired; QD-051 and QD-086 rejected.
- Hub to-do: the Mistral and Cloudflare keys are now recommended. By the afternoon the four channels use up the strong free
  models and the Lite fallback fails about 3 scripts in 8. Cerebras now needs a card, so it is not an option.

## Open
- Watch: round 1 verdicts and evolve's first settlements (analytics/round.csv, evolve.md, the hub's test table); the volume
  test from 8 November.
- tests/test_series.py section 12b read live data and broke on the 15:18 data commit (not a code change); being made
  hermetic. If it still fails, that is why.
- For Charlie (hub, "Your actions this week"): Facebook restriction check by 27 October (#34); TikTok reason by
  28 October (#35); Mistral key; Cloudflare key; IG_TOKEN by 10 December (#36); optional Music and Diario channels.

## Rules
CLAUDE.md "Channel rules" and "Working rules". Run every test before a push and push only on a clean run (a for-loop over
the tests does not fail the shell chain by itself). Commit as "Quickplay Studio" <quickplay-studio@users.noreply.github.com>.
