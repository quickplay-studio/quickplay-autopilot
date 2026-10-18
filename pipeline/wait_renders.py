"""Wait for GitHub to render the boards just pushed, in one command (run it in the background and get one result).
usage: python pipeline/wait_renders.py QD-101 QD-102 ...   (checks every 60 seconds, gives up after 50 minutes)
A board counts as done when its status/<id>.json was rendered after this command started. Then it pulls and prints one
line per Short: state, look, and any flag or error, so the lineup can be written straight from the output.
"""
import datetime as dt, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent

def remote_status(sid):
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:status/{sid}.json"], capture_output=True, text=True)
    try: return json.loads(r.stdout) if r.returncode == 0 else {}
    except ValueError: return {}

def main(ids):
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()      # pushes just before this count
    left, done = set(ids), {}
    for _ in range(50):
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", "main"], capture_output=True)
        for sid in list(left):
            st = remote_status(sid)
            if st.get("rendered", "") >= start and not st.get("state", "").startswith("waiting"):
                done[sid] = st; left.discard(sid)
        if not left: break
        time.sleep(60)
    subprocess.run(["git", "-C", str(ROOT), "pull", "-q", "--rebase", "origin", "main"], capture_output=True)
    for sid in ids:
        st = done.get(sid)
        if not st: print(f"{sid} | not rendered yet (still queued or rendering)"); continue
        flags = [f for f in st.get("flags") or [] if not f.startswith("approval is on")]
        look = st.get("look") or {}
        print(f"{sid} | {st.get('state')} | {(st.get('qa') or {}).get('duration', '?')} s | "
              f"{', '.join(f'{k} {v}' for k, v in look.items())} | {st.get('title', '')}"
              + (f" | flags: {'; '.join(flags)}" if flags else "") + (f" | error: {st.get('error')}" if st.get("error") else ""))

if __name__ == "__main__":
    main(sys.argv[1:])
