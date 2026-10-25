# Claude Code project template (lean on usage)

1. Copy it in: `cp -r templates/claude-code-project/. /path/to/new-project/` (the `/.` brings the hidden .claude folder).
2. Fill the `<...>` gaps in CLAUDE.md: the status command, the test command, the project map, the rules.
3. Edit .claude/settings.json: keep `"model": "sonnet"`, change the allow list to your test and build commands.
4. The four Haiku agents in .claude/agents (logs, data, tests, docs) read CLAUDE.md, so they need no edits.
5. Commit CLAUDE.md and .claude, then `cd` into the project and run `claude` (sign in once with your Max account).
6. `/agents` lists the four, `/model` shows Sonnet. Type `/effort low` for routine asks, `/effort medium` for risky edits.
7. Habits: `/clear` between tasks, `/compact` mid-task, and ask for "the logs agent" or "the data agent" first.
8. Once a week run `/usage`; if a session ran long, trim CLAUDE.md or tighten an agent.
9. Every project at once: put `{"model": "sonnet"}` in ~/.claude/settings.json (on your Mac, not in the repo).
10. Installs: pip with `--uploaded-prior-to P7D`, npm with `--before` 7 days ago (the supply-chain rule in quickplay-autopilot).
