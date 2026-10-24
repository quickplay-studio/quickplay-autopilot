"""Offline test of the alerts workflow's lighter shape (audit P5, 24 October): a runner starts only for a failed run, the
evening check and a 2-hourly recovery check; the recovery check closes a job's "is failing" issue once its latest run
succeeded; a timed-out run counts as a failure; alerts.yml's job condition and crons say so."""
import pathlib as _p, re, sys, types, json, os
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import alerts as A

OPEN = {"⚠️ render is failing (making the videos)": 5, "⚠️ social is failing (posting to Instagram and Facebook)": 6,
        "⚠️ A pipeline stage is stuck": 7}
LAST = {"render": "success", "social": "failure"}
CLOSED, RAISED = [], []
A.open_issues = lambda: dict(OPEN)
def gh(*a):
    if a[:2] == ("run", "list"):
        wf = a[a.index("--workflow") + 1].removesuffix(".yml")
        limit = int(a[a.index("--limit") + 1])
        return types.SimpleNamespace(stdout=json.dumps([{"conclusion": LAST.get(wf, "failure"), "url": f"https://x/{wf}"}] * limit), returncode=0)
    return types.SimpleNamespace(stdout="", returncode=0)
A.gh = gh
A.clear = lambda title, body: CLOSED.append(title)
A.raise_issue = lambda title, body, labels=None: RAISED.append(title)

A.recovered()
assert CLOSED == ["⚠️ render is failing (making the videos)"], CLOSED          # social still fails; the stuck issue isn't a job's
# a timed-out run is a failure: two in a row raise the issue
os.environ.update(RUN_NAME="social", RUN_CONCLUSION="timed_out", RUN_URL="https://x/run")
LAST["social"] = "timed_out"
A.after_run()
assert RAISED == ["⚠️ social is failing (posting to Instagram and Facebook)"], RAISED
# the workflow: a runner only for failures, the evening and the recovery cron, which main() routes to recovered()
y = (_p.Path(REPO_DIR) / ".github" / "workflows" / "alerts.yml").read_text()
assert "github.event_name != 'workflow_run' || contains(fromJSON('[\"failure\", \"timed_out\", \"startup_failure\"]'), github.event.workflow_run.conclusion)" in y
assert f"cron: '{A.RECOVERY_CRON}'" in y and "SCHEDULE: ${{ github.event.schedule }}" in y
print("alerts recovery ok")
