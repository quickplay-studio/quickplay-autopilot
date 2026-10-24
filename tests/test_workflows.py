"""Offline test of the workflow files themselves:
1. every github.event.schedule a step compares with is one of that workflow's crons (23 October: clips.yml compared
   with "1 17,18,21,22 * * *" while the cron said "1 17,18,19,21,22 * * *", so the social branch never ran and no clip
   was posted or submitted for days);
2. the supply-chain rule (CLAUDE.md, Black October): every pip install runs pip 26.2.1 first and uses
   --uploaded-prior-to P7D unless every package on the line is pinned exactly; npm global installs use --before;
3. every file is valid YAML and every run: block is valid bash."""
import pathlib as _p, re, subprocess, sys
try: import yaml
except ImportError: yaml = None                    # without PyYAML: the cron and install checks still run, the bash one not
REPO = _p.Path(__file__).resolve().parent.parent
WF = sorted((REPO / ".github" / "workflows").glob("*.yml"))
assert WF, "no workflows found"

bad = []
for p in WF:
    text = p.read_text()
    d = yaml.safe_load(text) if yaml else {}
    crons = set(re.findall(r"^\s*-\s*cron:\s*'([^']+)'", text, re.M))
    # 1. schedule comparisons, in expressions (== 'x') and in shell ("${{ github.event.schedule }}" = "x")
    named = set(re.findall(r"github\.event\.schedule\s*==\s*'([^']+)'", text))
    named |= set(re.findall(r"\$\{\{\s*github\.event\.schedule\s*\}\}\"?\s*=\s*\"([^\"]+)\"", text))
    for n in sorted(named - crons): bad.append(f"{p.name}: compares github.event.schedule with '{n}', which is not one of its crons {sorted(crons)}")
    # 2. supply chain
    for line in text.splitlines():
        for cmd in re.split(r"&&|;|\|\|", line):
            if "pip install" not in cmd: continue
            words, pkgs, skip = cmd.split("install", 1)[1].split(), [], False
            for t in words:
                if skip: skip = False; continue
                if t in ("--index-url", "--extra-index-url", "-i", "--uploaded-prior-to", "-r", "-c"): skip = True; continue
                if t.startswith("-"): continue
                pkgs.append(t.strip("\"'"))
            if pkgs == ["pip==26.2.1"]: continue
            pinned = bool(pkgs) and all("==" in t for t in pkgs)
            if "--uploaded-prior-to P7D" not in cmd and not pinned and "-r " not in cmd:
                bad.append(f"{p.name}: pip install without --uploaded-prior-to P7D: {cmd.strip()[:120]}")
            if "-r " in cmd and "--uploaded-prior-to P7D" not in cmd:
                bad.append(f"{p.name}: requirements install without --uploaded-prior-to P7D: {cmd.strip()[:120]}")
        if re.search(r"python -m pip install(?! -q pip==)", line) and "pip==26.2.1" not in line:
            bad.append(f"{p.name}: pip install without pip 26.2.1 first: {line.strip()[:120]}")
        if re.search(r"npm (install|i) -g", line) and "--before" not in line:
            bad.append(f"{p.name}: npm global install without --before: {line.strip()[:120]}")
    # 3. bash syntax of every run block (GitHub expressions replaced)
    for job in (d.get("jobs") or {}).values():
        for st in job.get("steps") or []:
            if not st.get("run"): continue
            r = subprocess.run(["bash", "-n"], input=re.sub(r"\$\{\{.*?\}\}", "X", st["run"]), text=True, capture_output=True)
            if r.returncode: bad.append(f"{p.name}: step '{st.get('name', st['run'][:40])}' is not valid bash: {r.stderr.strip()[:160]}")
assert not bad, "\n".join(bad)
print(f"workflows ok ({len(WF)} files)")
