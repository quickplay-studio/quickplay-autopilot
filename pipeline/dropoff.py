"""Where viewers swipe away (Charlie, 19 October): each Short's audience retention matched to its beats, as guidance
the writer reads on every run, so the advice moves with the data.

analytics.py already fetches each Short's retention curve (YouTube Analytics: the share of viewers still watching along
the video) into analytics/cache/youtube.json. Matched to the Short's timeline (status: each beat's start and end, and
whether a graphic card was on screen), it shows how fast viewers leave during graphic cards against photos, in the first
3 seconds against the rest, and in each beat. analytics/dropoff.json holds the numbers and, once 8 or more Shorts are
measured and a difference is clear (25% or more), plain guidance for writer.py.
  python pipeline/dropoff.py        (analytics.yml, after analytics.py)
"""
import datetime as dt, json, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "analytics" / "dropoff.json"
NOW = dt.datetime.now(dt.timezone.utc)
MIN_SHORTS, CLEAR = 8, 1.25


def statuses():
    out = {}
    for p in (ROOT / "status").glob("QD-*.json"):
        try: st = json.loads(p.read_text())
        except Exception: continue
        if st.get("video"): out[st["video"]] = st
    return out


def curves():
    """{video: [[fraction of the video, share still watching], ...]} from analytics.py's cache."""
    try: c = json.loads((ROOT / "analytics" / "cache" / "youtube.json").read_text())
    except Exception: return {}
    return {v: sorted([float(k), float(x)] for k, x in cv.items()) for v, cv in (c.get("retention") or {}).items() if cv}


def at(curve, x):
    """Share of viewers still watching at fraction x of the video (straight lines between YouTube's points)."""
    pts = [(0.0, curve[0][1])] + [tuple(p) for p in curve]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1: return y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0)
    return pts[-1][1]


def analyse(cv, by_video):
    vis, beat, first, rest, n = {"graphic": [], "photo": []}, {}, [], [], 0
    for vid, curve in cv.items():
        st = by_video.get(vid) or {}
        tl, dur = st.get("timeline") or [], float((st.get("qa") or {}).get("duration") or 0)
        if len(curve) < 10 or not tl or dur < 8: continue
        n += 1
        def loss(a, b):     # % of the viewers there at second a who leave each second until b
            ya, yb = at(curve, a / dur), at(curve, b / dur)
            return max(0.0, ya - yb) / max(ya, 1e-6) / max(b - a, 0.1) * 100
        first.append(loss(0, 3)); rest.append(loss(3, dur))
        for i, seg in enumerate(tl):
            s, e, vt = float(seg[0]), float(seg[1]), str(seg[2])
            if e - s < 0.8: continue
            x = loss(s, e)
            vis["photo" if vt == "none" else "graphic"].append(x)
            beat.setdefault(i + 1, []).append(x)
    med = lambda xs: round(statistics.median(xs), 2) if xs else None
    res = {"updated": NOW.isoformat(timespec="minutes"), "shorts": n,
           "lost_per_second": {"graphic cards": med(vis["graphic"]), "photos": med(vis["photo"]), "first 3 seconds": med(first),
                               "after 3 seconds": med(rest), **{f"beat {i}": med(v) for i, v in sorted(beat.items()) if len(v) >= 3}},
           "guidance": []}
    if n < MIN_SHORTS: return res
    g, p, f, r, out = med(vis["graphic"]), med(vis["photo"]), med(first), med(rest), res["guidance"]
    if g and p and len(vis["graphic"]) >= 5:
        if g > p * CLEAR:
            out.append(f"Viewers leave faster during graphic cards ({g:.1f}% a second) than over photos ({p:.1f}%): use fewer cards and keep them short.")
        elif p > g * CLEAR:
            out.append(f"Graphic cards hold viewers better than photos ({g:.1f}% against {p:.1f}% a second): a card is worth it wherever there is a figure to show.")
    if f and r and f > r * 1.5:
        out.append(f"The first 3 seconds lose the most viewers ({f:.1f}% a second against {r:.1f}% later): the hook and the first picture decide the Short.")
    later = {i: med(v) for i, v in beat.items() if len(v) >= 5 and i > 1}
    if later and r:
        i = max(later, key=later.get)
        if later[i] > r * CLEAR:
            out.append(f"Beat {i} loses the most viewers after the hook ({later[i]:.1f}% a second): keep it short and get to the point.")
    return res


def main():
    res = analyse(curves(), statuses())
    OUT.write_text(json.dumps(res, indent=1))
    print(f"drop-off: {res['shorts']} Shorts measured;", " ".join(res["guidance"]) or "no guidance yet")


if __name__ == "__main__":
    main()
