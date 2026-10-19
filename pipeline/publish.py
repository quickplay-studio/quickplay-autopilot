"""Upload the Shorts that waited for Charlie's approval, and drop the ones he turned down.

Decisions come from text files in approvals/ (one per line; the daily session writes them when Charlie replies) or from
the "decision" box of the publish workflow on GitHub (Actions, publish, Run workflow):
  approve all                        every Short waiting in boards/ready
  approve all except QD-031 QD-034   approve the rest; the listed ones are dropped
  approve QD-031 QD-033              (or just: approve 31 33)
  reject QD-032                      dropped: preview deleted, board moved to boards/rejected
Approved Shorts upload from their preview render (draft release preview-<id>) into the next free slot, within the daily
upload limit. Ones that don't fit wait, and the hourly run tries again. Applied decision files move to approvals/applied.

Reserve: evergreen Shorts written with "reserve": true render like any other but wait in boards/reserve. Charlie approves
them in advance ("reserve approve all", "reserve approve QD-030", "reserve reject QD-031"). On a day when nothing new was
written by the evening (config reserve_after, UK time; for example every writer run was blocked by a usage limit), the
oldest approved ones (config reserve_per_day) are released and upload like approved Shorts.
usage: python pipeline/publish.py
"""
import datetime as dt, json, os, pathlib, re, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import plan

NOW = dt.datetime.now(dt.timezone.utc)
READY, STATUS, RESERVE = ROOT / "boards" / "ready", ROOT / "status", ROOT / "boards" / "reserve"

def gh(*args, check=True):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)

def ids_in(text):
    tests = [m.group(0).upper() for m in re.finditer(r"\bTEST-[A-Z0-9-]+\b", text, re.I)]
    rest = re.sub(r"\bTEST-[A-Z0-9-]+\b", " ", text, flags=re.I)
    return tests + [f"QD-{int(m.group(1)):03d}" for m in re.finditer(r"\b(?:QD-?)?(\d{1,4})\b", rest, re.I)]

def parse(line, waiting):
    """(approved ids, rejected ids) for one decision line."""
    l = line.strip().lower()
    if not l or l.startswith("#"): return set(), set()
    if re.match(r"(approve|approved|yes|ok|okay|go)\b", l):
        if re.search(r"\ball\b", l):
            dropped = set(ids_in(l.split("except", 1)[1])) & waiting if "except" in l else set()
            return waiting - dropped, dropped
        return set(ids_in(l)) & waiting, set()
    if re.match(r"(reject|rejected|drop|skip|no)\b", l):
        return set(), set(ids_in(l)) & waiting
    return set(), set()

def load_status(i):
    p = STATUS / f"{i}.json"
    return json.loads(p.read_text()) if p.exists() else {"id": i}

def save_status(st):
    STATUS.mkdir(exist_ok=True)
    (STATUS / f"{st['id']}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))

def move(board, folder):
    dest = ROOT / "boards" / folder; dest.mkdir(exist_ok=True)
    shutil.move(str(board), str(dest / board.name))

def is_reserve_line(l):
    return l.strip().lower().startswith("reserve")

def reserve_step(lines):
    """Apply reserve decisions; in the evening, fill the slots the day's writer runs left empty with the oldest cleared
    reserve Shorts (approved by Charlie, or in "flagged" mode simply not flagged), at most reserve_per_day a day."""
    boards = {}
    for p in sorted(RESERVE.glob("*.json")):
        try: boards[json.loads(p.read_text())["id"]] = p
        except Exception: pass
    if not boards: return
    status = {i: load_status(i) for i in boards}
    waiting = {i for i in boards if not status[i].get("reserve_approved")}
    for l in lines:
        a, r = parse(re.sub(r"^\s*reserve\s*", "", l, flags=re.I), set(boards))
        for i in sorted(a & waiting):
            status[i].update(reserve_approved=NOW.isoformat(timespec="seconds"), state="in reserve (approved)"); save_status(status[i])
            print(i, "approved into the reserve")
        for i in sorted(r):
            st = status[i]
            if st.get("preview_release"): gh("release", "delete", st["preview_release"], "-y", check=False)
            st.pop("preview_release", None); st.pop("preview_url", None)
            st.update(state="rejected", rejected=NOW.isoformat(timespec="seconds")); save_status(st)
            move(boards.pop(i), "rejected"); print(i, "rejected from the reserve")
    uk = NOW.astimezone(plan.UK); today = str(uk.date())
    after = dt.datetime.strptime(plan.CFG.get("reserve_after", "18:20"), "%H:%M").time()
    if uk.time() < after: return
    made = 0                                                 # today's Shorts from the writer runs
    for d in ("queue", "ready", "done"):
        for p in (ROOT / "boards" / d).glob("QD-*.json"):
            try: b = json.loads(p.read_text())
            except Exception: continue
            if b.get("created") == today and not b.get("reserve"): made += 1
    used = sum(1 for d in ("ready", "done") for p in (ROOT / "boards" / d).glob("QD-*.json") if load_status(p.stem).get("from_reserve") == today)
    want = int(plan.CFG.get("daily_limit", 24)) - (1 if uk.weekday() == 6 else 0)     # Sundays keep one for the weekly video
    gap = min(int(plan.CFG.get("reserve_per_day", 3)) - used, want - made - used)
    if gap <= 0: return
    auto = plan.CFG.get("approval", "flagged") in ("flagged", "none")
    def cleared(i):         # approved by Charlie, or (flagged mode) nothing flagged, like any other Short
        return status[i].get("reserve_approved") or (auto and not [f for f in status[i].get("flags") or [] if not f.startswith("reserve")])
    ready = sorted((i for i in boards if cleared(i) and status[i].get("preview_release")),
                   key=lambda i: status[i].get("reserve_approved") or status[i].get("rendered") or "")
    for i in ready[:gap]:
        st = status[i]
        st.update(approved=NOW.isoformat(timespec="seconds"), from_reserve=today, state="approved, uploading (from the reserve)")
        save_status(st); move(boards[i], "ready"); print(i, f"released from the reserve: today had {made} of {want} Shorts")

def main():
    files = sorted((ROOT / "approvals").glob("*.txt")) if (ROOT / "approvals").exists() else []
    lines = [l for f in files for l in f.read_text().splitlines()]
    if os.environ.get("DECISION", "").strip(): lines.append(os.environ["DECISION"])
    reserve_step([l for l in lines if is_reserve_line(l)])
    done_files = [f for f in files if all(is_reserve_line(l) for l in f.read_text().splitlines() if l.strip())]
    if done_files:                    # files holding only reserve decisions are finished with
        applied = ROOT / "approvals" / "applied"; applied.mkdir(parents=True, exist_ok=True)
        for f in done_files: f.replace(applied / f"{NOW:%Y%m%d-%H%M%S}-{f.name}")
        files = [f for f in files if f not in done_files]
    lines = [l for l in lines if not is_reserve_line(l)]
    ready = {}
    for p in sorted(READY.glob("*.json")):
        try: ready[json.loads(p.read_text())["id"]] = p
        except Exception: pass
    if not ready:
        print("nothing waiting for approval"); return
    status = {i: load_status(i) for i in ready}

    # 1. Charlie's decisions
    approve, reject = set(), set()
    for l in lines:
        a, r = parse(l, set(ready)); approve |= a; reject |= r
    approve -= reject
    for i in sorted(approve):
        if not status[i].get("approved"):
            status[i]["approved"] = NOW.isoformat(timespec="seconds"); status[i]["state"] = "approved, uploading"
            save_status(status[i])
    for i in sorted(reject):
        st = status[i]
        if st.get("preview_release"): gh("release", "delete", st["preview_release"], "-y", check=False)
        st.pop("preview_release", None); st.pop("preview_url", None)
        st.update(state="rejected", rejected=NOW.isoformat(timespec="seconds"))
        save_status(st); move(ready.pop(i), "rejected"); print(i, "rejected")
    if files:
        applied = ROOT / "approvals" / "applied"; applied.mkdir(parents=True, exist_ok=True)
        for f in files: f.replace(applied / f"{NOW:%Y%m%d-%H%M%S}-{f.name}")

    # 2. Upload what's approved
    todo = [i for i in sorted(ready) if status[i].get("approved")]
    if not todo:
        print("waiting for approval:", ", ".join(sorted(ready))); return
    import youtube as Y
    if not Y.available():
        print("YouTube keys missing"); return
    yt = Y.client()
    taken, recent, _ = plan.schedule_state(NOW, yt)
    capacity = max(0, plan.LIMIT - recent)
    next_slot = plan.slot_picker(NOW, taken)
    on_channel = {v["title"].strip().lower(): v["id"] for v in Y.recent_videos(yt, limit=100)}
    print(f"approved: {len(todo)}, room today: {capacity}")
    for i in todo:
        st, board = status[i], ready[i]
        b = json.loads(board.read_text())
        tag = st.get("preview_release")
        if capacity <= 0:
            st["state"] = "approved, waiting for YouTube's daily upload limit"; save_status(st); continue
        if not tag:
            st["state"] = "approved, but the preview render is missing (re-queue the board)"; save_status(st); continue
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            r = gh("release", "download", tag, "-D", str(tmp), "--clobber", check=False)
            if r.returncode or not (tmp / "video.mp4").exists() or not (tmp / "upload.json").exists():
                st.update(state="approved, but the preview render is missing (re-queue the board)", error=r.stderr.strip()[:200])
                save_status(st); continue
            u = json.loads((tmp / "upload.json").read_text())
            if b.get("mode") == "dry":     # approval-path test: everything except the upload itself
                for asset in ("video.mp4", "upload.json"): gh("release", "delete-asset", tag, asset, "-y", check=False)
                left = gh("release", "view", tag, "--json", "assets", "-q", "[.assets[].name]", check=False).stdout.strip()
                gh("release", "delete", tag, "-y", check=False)
                st.update(state="approved (dry run, not uploaded)", dry_run={"downloaded": sorted(x.name for x in tmp.iterdir()),
                          "assets_left_after_cleanup": left, "would_upload_title": u["title"], "tags": len(u.get("tags", []))})
                st.pop("preview_release", None); st.pop("preview_url", None)
                save_status(st); move(board, "done"); print(i, st["state"]); continue
            dup = on_channel.get(u["title"].strip().lower())
            if dup:
                st.update(state="already on YouTube (not uploaded again)", video=dup, url=f"https://youtube.com/shorts/{dup}")
                gh("release", "delete", tag, "-y", check=False); st.pop("preview_release", None)
                save_status(st); move(board, "done"); continue
            slot = None
            if b.get("mode", "schedule") == "schedule":
                t = None
                if b.get("publish_at"):
                    t = dt.datetime.strptime(b["publish_at"], "%Y-%m-%d %H:%M").replace(tzinfo=plan.UK).astimezone(dt.timezone.utc)
                    if t < NOW + dt.timedelta(minutes=45) or t in taken: t = None
                    else: taken.add(t)
                slot = (t or next_slot(b.get("created"))).isoformat().replace("+00:00", "Z")
            try:
                vid = Y.upload(yt, tmp / "video.mp4", u["title"], u["description"], u["tags"], u["category"], slot, localizations=u.get("localizations"))
            except Y.LimitReached:
                st["state"] = "approved, waiting for YouTube's daily upload limit"; save_status(st); capacity = 0; continue
            except Exception as e:
                st["upload_attempts"] = st.get("upload_attempts", 0) + 1
                st.update(state="approved, upload failed (retrying hourly)", error=f"{type(e).__name__}: {e}"[:400])
                if st["upload_attempts"] >= 3:
                    st["state"] = "upload failed"; save_status(st); move(board, "failed")
                else: save_status(st)
                continue
            capacity -= 1
            st.pop("error", None)
            st.update(uploaded_at=NOW.isoformat(timespec="seconds").replace("+00:00", "Z"), video=vid,
                      url=f"https://youtube.com/shorts/{vid}", publish_at=slot,
                      state="scheduled" if slot else "uploaded (private)")
            try:
                kept = Y.video_status(yt, vid); st["youtube"] = kept
                if slot and not kept.get("publish_at"): st["state"] = "uploaded but not scheduled (check Studio)"
            except Exception as e:
                st["youtube"] = {"error": str(e)[:200]}
            # The release now only carries the TikTok and Instagram version (social.py posts it once the Short is public).
            for asset in ("video.mp4", "upload.json"): gh("release", "delete-asset", tag, asset, "-y", check=False)
            if (tmp / "social.mp4").exists(): st["social_release"] = tag
            else: gh("release", "delete", tag, "-y", check=False)
            st.pop("preview_release", None); st.pop("preview_url", None)
            save_status(st); move(board, "done")
            print(i, st["state"], slot or "", st["url"])

if __name__ == "__main__":
    main()
