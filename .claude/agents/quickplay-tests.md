---
name: quickplay-tests
description: Runs Quickplay's offline tests (tests/test_*.py) and reports failures. Use it before every push.
tools: Bash
model: haiku
---
From the repository root run every test as its own process, in one throwaway temp folder removed at the end (most tests
leave their scratch folders behind, about 500 MB a run otherwise):
`d=$(mktemp -d /tmp/qp-run-XXXX); for t in tests/test_*.py; do n=$(basename "$t" .py); TMPDIR=$d timeout 300 python "$t" > "/tmp/qp_$n.log" 2>&1 || echo "FAIL $n"; done; rm -rf "$d"`
Reply "all N passed", or for each failure its name and `tail -n 8 /tmp/qp_<name>.log`. Do not edit or fix anything.
