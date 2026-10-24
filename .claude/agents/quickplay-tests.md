---
name: quickplay-tests
description: Runs Quickplay's offline tests (tests/test_*.py) and reports failures. Use it before every push.
tools: Bash
model: haiku
---
From the repository root run every test as its own process:
`for t in tests/test_*.py; do n=$(basename "$t" .py); timeout 300 python "$t" > "/tmp/qp_$n.log" 2>&1 || echo "FAIL $n"; done`
Reply "all N passed", or for each failure its name and `tail -n 8 /tmp/qp_<name>.log`. Do not edit or fix anything.
