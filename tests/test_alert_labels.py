"""alerts.raise_issue labels (24 October): issues only Charlie can act on carry "needs-charlie", which the hub's Overview
lists under "Your actions this week". Offline: gh is stubbed."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pipeline"))
import alerts as A

CALLS, OPEN = [], {}
A.gh = lambda *a: CALLS.append(a) or type("R", (), {"stdout": "", "stderr": "", "returncode": 0})()
A.open_issues = lambda: dict(OPEN)

# 1. a plain alert is opened exactly as before: one "alert" label, no other label made
A.raise_issue("⚠️ Something", "body")
create = [c for c in CALLS if c[:2] == ("issue", "create")]
assert len(create) == 1 and list(create[0]).count("--label") == 1 and "alert" in create[0], create
assert not [c for c in CALLS if c[:2] == ("label", "create") and c[2] != "alert"], CALLS

# 2. needs-charlie: the label is made and the new issue carries both labels
CALLS.clear()
A.raise_issue("🔑 A sign-in has expired: reconnect it", "body", labels=["needs-charlie"])
assert ("label", "create", "needs-charlie") == CALLS[0][:3], CALLS
create = [c for c in CALLS if c[:2] == ("issue", "create")][0]
labels = [create[i + 1] for i, x in enumerate(create) if x == "--label"]
assert labels == ["alert", "needs-charlie"], labels

# 3. an issue already open gets a comment and gains the label (it may predate the label)
CALLS.clear(); OPEN["🔑 A sign-in has expired: reconnect it"] = 7
A.raise_issue("🔑 A sign-in has expired: reconnect it", "again", labels=["needs-charlie"])
assert ("issue", "comment", "7", "--body", "again") in CALLS, CALLS
assert ("issue", "edit", "7", "--add-label", "needs-charlie") in CALLS, CALLS
assert not [c for c in CALLS if c[:2] == ("issue", "create")]

# 4. the call sites that need Charlie pass the label (identity, submit logins, the Facebook key)
root = pathlib.Path(__file__).resolve().parent.parent / "pipeline"
for f, n in (("identity.py", 2), ("submit.py", 1), ("alerts.py", 1)):
    assert (root / f).read_text().count('labels=["needs-charlie"]') == n, f

# 5. status/actions.json is a list the hub can read, with the fields it shows
import json
items = json.loads((root.parent / "status" / "actions.json").read_text())
assert isinstance(items, list) and items
for a in items:
    assert {"id", "title", "why", "steps", "links", "added", "due", "done"} <= set(a), a.get("id")
    assert a["due"] == "" or len(a["due"]) == 10
    assert not any(chr(c) in json.dumps(a, ensure_ascii=False) for c in (0x2013, 0x2014)), a["id"]     # no en or em dashes
assert len({a["id"] for a in items}) == len(items)
print("alert labels: ok")
