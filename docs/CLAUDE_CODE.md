# Claude Code for Quickplay (25 October 2026)

**Verdict.** Yes, it can cut your usage, but the app does nothing by itself. What saves usage is behaviour: the model,
the size of the context, short sessions, cheap helpers and no whole-file reads. Claude Code lets you set each of those in
one place and keep it set. Opening the same long Opus chat in Claude Code saves nothing. Test it: note `/usage` today and
again after a week.

## Why it can cut usage
1. **Model.** Max defaults to Opus. Sonnet does this repo's work (reading logs, small edits) for much less usage a turn.
   `.claude/settings.json` sets `"model": "sonnet"`, so every session here starts on it.
2. **Effort.** `/effort low` trims thinking on routine asks. The repo default is low (`effortLevel`); type
   `/effort medium` before a risky change to pipeline/.
3. **Context.** Each turn re-reads the whole conversation, so a long chat costs more per message than a fresh one.
   `/clear` between tasks; `/compact` when you must keep the thread.
4. **Haiku agents.** .claude/agents holds quickplay-logs, -data, -tests and -docs, all `model: haiku`. A log or CSV is
   read in their small context at the cheapest model; only a 10-line answer returns to yours. Subagents count towards the
   same limits, so the gain is the cheaper model and a small main context, not free work.
5. **No whole-file reads.** CLAUDE.md's token budget says digest first, aggregates only. Here that is also enforced: tokens/
   and .env are denied to the Read tool, and installs and pushes ask first.

Skills in place of a long CLAUDE.md are the next step if this one grows (the costs page recommends it); today it is
about 1,100 words, which is fine.

## What it cannot change
- **One pool.** claude.ai, Cowork, Claude Code and the pipeline's `CLAUDE_CODE_OAUTH_TOKEN` calls all draw on your single
  Max allowance (support.claude.com/en/articles/11014257). Changing app moves nothing to a different pool.
- **A big ask costs the same anywhere.** Claude Code loops (run, read, retry) can spend more than a chat answer. Press
  Esc to stop one; `/usage` shows what it cost.
- **Cowork's starting context** likely carries more (connectors, browser tools). I have not measured the gap.
- The code.claude.com docs pages could not be fetched when this was written, so the settings keys and rule syntax were
  checked against the installed CLI (2.1.310) instead. If a key is ever reported as unknown, `/doctor` says which.

## Setup on your Mac (once)
1. `node -v` should print 18 or higher. If it fails, tell the next session; installing Node is a download we ask about.
2. Install, keeping the supply-chain rule (no curl-pipe-sh): `npm install -g @anthropic-ai/claude-code@2.1.302
   --before="$(date -u -v-7d +%Y-%m-%d)"`. That is the version the pipeline pins; move the pin after a week of a newer one.
3. `cd` into the quickplay-autopilot folder on your Mac, then `claude`. Sign in with your Max account in the browser
   (your own login, nothing is typed into the terminal) and trust the folder.
4. The header should say Sonnet. If not, `/model sonnet`. `/effort low` is already the default here.
5. `/agents` should list the four quickplay-* agents. `/usage` shows your allowance.
6. Optional, every project: put `{"model": "sonnet"}` in `~/.claude/settings.json`.

Habits: `/clear` when the task changes; `/compact keep the file list and what is left` mid-task; start asks with the
agent's name; run `/usage` on Sundays; close a session you are not using.

## The three asks you make most
**What's broken**
> Use quickplay-logs: what failed in the last 24 hours and why? Tell me only what needs me, with the fix steps.

**Change X**
> Change: <X>. Read CLAUDE.md first. Find the code with grep, edit it, then have quickplay-tests run everything and
> quickplay-docs write the NEXT.md line. Commit as Quickplay Studio. Do not push until I say.

**How are the numbers**
> Use quickplay-data: <question, e.g. views a day this week against last, by platform>. Ten lines, and say how many
> Shorts each number rests on.

For a risky change, add `/effort medium` first and `/clear` straight after.

## Scheduled tasks and the portal
| Route | Model | Context | Best for |
|---|---|---|---|
| Scheduled tasks (Cowork) | Sonnet now | a fresh session every firing, so the prompt must stand alone | recurring reviews, such as docs/WEEKLY_REVIEW.md, when the Mac is shut |
| The portal (pinned Quickplay page, quickplay skill) | Sonnet now | one request at a time | a change or question sent from your phone |
| Claude Code on the Mac | Sonnet, your choice | the repo's CLAUDE.md and agents, nothing else | live sessions where you would have used Opus or kept a long chat |

Scheduled tasks and the portal already run on the cheap model, so moving them gains little. Claude Code pays off where you
choose the model and the length of the session yourself. Keep the other two for work that must happen away from the Mac.

## Headless `claude -p` for automation
It draws on the same subscription when it signs in with `CLAUDE_CODE_OAUTH_TOKEN` (made by `claude setup-token`), so a
script that runs often spends your allowance like a person typing often. The pipeline already does this once:
factpack.claude_call runs `claude -p --model sonnet --tools "" --max-turns 2` in an empty folder (so no CLAUDE.md or
settings.json is loaded), capped at 4 edits a day and 3 calls a run, and takes the Messages API instead when an
`ANTHROPIC_API_KEY` secret exists (billed apart from the pool). The CLI is pinned to 2.1.302 because `--bare`, which
ignores OAuth sign-ins, is due to become the default. For any new automation: name the model, set `--max-turns`, allow no
tools unless needed, run in an empty folder, count calls in a status file and cap them per day.

## Next project
Copy `templates/claude-code-project/` (README.md there: ten lines). It holds a short CLAUDE.md with the token budget first,
the four generic Haiku agents and a settings.json that defaults to Sonnet.
