# <Project>: how it runs (<date>)

<One or two sentences: what it does, what runs by itself, when a Claude session is needed.>

## Token budget (read first)
- Default model Sonnet (settings.json). `/effort low` for routine asks, `/clear` between tasks, `/compact` mid-task,
  `/usage` once a week.
- Read this file, then run `<one-screen status command>`. Never open a data file whole (<list them>): `head -1`, `tail`,
  `grep` or a one-line aggregate.
- Hand log reading, number questions, test runs and dated doc lines to the Haiku agents in .claude/agents (logs, data,
  tests, docs) so only their short answers reach this context.
- Keep this file under 100 lines. Move rarely needed detail to docs/ and link it.

## Project map
| Path | What it holds |
|---|---|
| `<src/>` | <code> |
| `<data/>` | <data files; what each column means> |
| `<docs/CHANGES.md>` | change log, newest at the bottom |

## Commands
- Status: `<one-screen status command>`
- Tests: `<test command>` (run before every push)

## Rules (non-negotiable)
- <The few things that must never happen: legal, safety, brand, spelling, secrets.>

## Working rules
- Terse, conclusion-first replies. Ask before anything public, any purchase or any new dependency.
- Run the tests, then commit, then `git pull --rebase`, then push. Never break the next scheduled run.
- Secrets live in the host's secret store, never in files or chat.

## Change ledger (optional)
Every change pushed gets one row: what, why it should help, the number it should move, what must not get worse. The
docs agent writes it with `<ledger command>`. Delete this section if the project has no numbers to judge a change by.
