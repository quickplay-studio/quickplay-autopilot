"""One compact read of where things stand, so a writer run never has to open status files one by one.
usage: python pipeline/digest.py
Prints: the health line, boards per folder, Shorts made for today and tomorrow, anything
failed or waiting with its reason, the last two days' Shorts one line each, and the current breakouts.
"""
import csv, datetime as dt, io, json, pathlib, subprocess, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)

def load(p):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return {}

def uk(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(UK).strftime("%a %H:%M")
    except Exception: return ""

def main():
    try: print(subprocess.run([sys.executable, str(ROOT / "pipeline" / "health.py")], capture_output=True, text=True, timeout=60).stdout.strip())
    except Exception: pass
    today = NOW.astimezone(UK).date(); tomorrow = today + dt.timedelta(days=1)
    folders, made = {}, {str(today): [0, 0], str(tomorrow): [0, 0]}
    for d in ("queue", "ready", "done", "failed", "reserve", "rejected", "expired"):
        files = list((ROOT / "boards" / d).glob("QD-*.json")); folders[d] = len(files)
        for f in files:
            b = load(f)
            if b.get("created") in made and d not in ("rejected", "expired") and not b.get("reserve"):
                made[b["created"]][0] += 1; made[b["created"]][1] += 1 if b.get("tiktok") else 0
    print("boards: " + ", ".join(f"{k} {v}" for k, v in folders.items()))
    print(f"made for today ({today}): {made[str(today)][0]} Shorts; for tomorrow ({tomorrow}): {made[str(tomorrow)][0]} Shorts")
    rows = []
    for p in (ROOT / "status").glob("QD-*.json"):
        st = load(p)
        when = st.get("uploaded_at") or st.get("rendered") or ""
        try: recent = NOW - dt.datetime.fromisoformat(str(when).replace("Z", "+00:00")) < dt.timedelta(hours=48)
        except Exception: recent = False
        if recent or st.get("state", "").startswith(("failed", "awaiting", "approved, waiting", "waiting")):
            rows.append(st)
    rows.sort(key=lambda s: s.get("id", ""))
    attention = [s for s in rows if s.get("state", "").startswith(("failed", "awaiting", "approved, waiting", "upload failed"))
                 and not (s.get("flags") or [""])[0].startswith("reserve")]
    if attention:
        print("needs attention:")
        for s in attention:
            why = s.get("error") or "; ".join(f for f in (s.get("flags") or []) if not f.startswith("approval is on"))
            print(f"  {s.get('id')} {s.get('state')}: {str(why)[:160]}")
    print("last 48 hours:")
    for s in rows[-60:]:
        print(f"  {s.get('id')} | {s.get('state', '?')[:28]} | {uk(s.get('publish_at'))} | {str(s.get('title') or '')[:60]}")
    bp = ROOT / "analytics" / "breakouts.csv"
    hot = list(csv.DictReader(io.StringIO(bp.read_text()))) if bp.exists() else []
    if hot:
        print("breakouts (follow up the strongest one not yet followed up):")
        for b in hot[:3]: print(f"  {b['short']} {b['times_typical']}x at {b['hours_public']} h: {b['title']}")
    else: print("breakouts: none right now")

if __name__ == "__main__":
    main()
