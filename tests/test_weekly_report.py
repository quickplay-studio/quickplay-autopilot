"""Offline test of the Monday report (pipeline/weekly_report.py): it builds from the repo's data files without opening an
issue, and carries every section."""
import pathlib as _p, subprocess, sys, os, tempfile
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
out = _p.Path(tempfile.mkdtemp(prefix="qp-test-")) / "weekly.md"
r = subprocess.run([sys.executable, REPO_DIR + "/pipeline/weekly_report.py"], env={**os.environ, "REPORT_ISSUE": "0", "REPORT_OUT": str(out)},
                   capture_output=True, text=True, cwd=REPO_DIR, timeout=120)
assert r.returncode == 0, r.stderr[-800:]
t = out.read_text()
for h in ("# Quickplay weekly:", "## The week in numbers", "## Is the optimisation working", "## What changed this week",
          "## Stopped", "## What every Short is measured on", "## Quickplay Clips", "Pages:"):
    assert h in t, h
assert "Shorts posted:" in t and "Rulings in force:" in t and "clips public" in t
print("weekly report ok")
