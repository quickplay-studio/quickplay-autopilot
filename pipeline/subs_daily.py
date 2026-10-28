"""The channel-day subscriber model (28 October, advisory only): subscribers are the Partner Programme's other blocker (18 of the
500 or 1,000 needed), and they are judged per Short today, where 170 of 184 measured Shorts gained none. A subscriber is
earned by a channel's viewers over a day, not by one Short, so this looks at the day.

analytics/subs_daily.csv, one row per channel and day: the subscribers the channel gained and lost that day and its views
(YouTube Analytics at channel level, the same read the headline uses; the other channels one extra Analytics query each, which
costs no Data API units), the Shorts posted that UK day, and for each factor of the round the share of that day's Shorts
that took arm B (blank when none of them took an arm), "share_<factor>". YouTube Analytics counts its days in Pacific time,
so a row's subscribers can include the end of the day before; the Shorts columns are UK days. The file keeps earlier days
the newest read no longer returns.

analytics/subs_model.md: a small ridge regression of subscribers gained per 1,000 views on the day's mix, within channel (each
channel's own average taken out), weighted by views, over channel-days with 100+ views; an arm's coefficient is the change in
subscribers per 1,000 views between a day of all arm B and a day of all arm A, with a 90% bootstrap interval (seeded). Few
channel-days and many factors means a wide interval: it says so, and nothing reads it yet (ledger target subs_day, changes.py).
Standard library only."""
import csv, datetime as dt, io, math, pathlib, random, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
UK = ZoneInfo("Europe/London")
BASE = ["channel", "day", "subs_gained", "subs_lost", "views", "engaged_views", "shorts"]
MIN_VIEWS, MIN_DAYS, PER_FACTOR, LAMBDA, BOOT, SEED, MAX_FACTORS = 100, 20, 4, 1.0, 300, 11, 14


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError): return None


def uk_day(r):
    try: return dt.datetime.fromisoformat(str(r["posted"])).astimezone(UK).date().isoformat()
    except (KeyError, ValueError, TypeError): return str(r.get("posted_day") or "")


def assigned(r, f):
    import drivers
    return drivers.assigned(r, f)


def share_cols(factors):
    return [f"share_{f}" for f in list(factors)[:MAX_FACTORS]]


def build(rows, daily_by_channel, factors):
    """[{channel, day, subs_gained, subs_lost, views, engaged_views, shorts, share_<factor>...}] for every channel day the
    Analytics read returns. rows: shorts.csv rows (channel, posted, the factor columns); daily_by_channel: {channel: [{"day",
    "views", "engagedViews", "subscribersGained", "subscribersLost"}]}; factors: {factor: [arm_a, arm_b]}."""
    factors = {f: a for f, a in list(factors.items())[:MAX_FACTORS] if len(a) == 2}
    by = {}
    for r in rows:
        by.setdefault(((r.get("channel") or "main"), uk_day(r)), []).append(r)
    out = []
    for ch, days in daily_by_channel.items():
        for d in days or []:
            day = str(d.get("day") or "")
            if not day: continue
            mine = by.get((ch, day), [])
            if not mine and not num(d.get("views")): continue          # a day before the channel had Shorts or views
            row = {"channel": ch, "day": day, "subs_gained": d.get("subscribersGained", ""), "subs_lost": d.get("subscribersLost", ""),
                   "views": d.get("views", ""), "engaged_views": d.get("engagedViews", ""), "shorts": len(mine)}
            for f, (a, b) in factors.items():
                taken = [assigned(r, f) for r in mine if assigned(r, f) in (a, b)]
                row[f"share_{f}"] = round(sum(x == b for x in taken) / len(taken), 3) if taken else ""
            out.append(row)
    return out


def merge(old, new, cols):
    """The earlier file's rows for days the new read does not return, then the new rows; sorted by channel and day."""
    keep = {(r.get("channel"), r.get("day")): {c: r.get(c, "") for c in cols} for r in old}
    for r in new: keep[(r["channel"], r["day"])] = {c: r.get(c, "") for c in cols}
    return [keep[k] for k in sorted(keep, key=lambda k: (str(k[0]), str(k[1])))]


def solve(A, y):
    """Gaussian elimination with partial pivoting; A is a square list of lists (ridge makes it positive definite)."""
    n = len(A)
    M = [list(A[i]) + [y[i]] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda i: abs(M[i][c]))
        if abs(M[piv][c]) < 1e-12: return None
        M[c], M[piv] = M[piv], M[c]
        for i in range(c + 1, n):
            f = M[i][c] / M[c][c]
            for j in range(c, n + 1): M[i][j] -= f * M[c][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def design(rows, cols):
    """(X, y, w, kept rows) for the ridge: channel-days with MIN_VIEWS views, each factor share missing filled with the
    channel's mean, then everything centred within channel (weighted by views), y = subscribers per 1,000 views."""
    use = []
    for r in rows:
        v, s = num(r.get("views")), num(r.get("subs_gained"))
        if v is None or s is None or v < MIN_VIEWS: continue
        use.append((r, v, 1000.0 * s / v))
    chans = sorted({r.get("channel") for r, _, _ in use})
    X, y, w, kept = [], [], [], []
    for ch in chans:
        mine = [(r, v, t) for r, v, t in use if r.get("channel") == ch]
        tot = sum(v for _, v, _ in mine)
        ybar = sum(v * t for _, v, t in mine) / tot
        means = []
        for c in cols:
            pts = [(num(r.get(c)), v) for r, v, _ in mine if num(r.get(c)) is not None]
            means.append(sum(x * v for x, v in pts) / sum(v for _, v in pts) if pts else 0.0)
        # the mean after filling is the same weighted mean, so a missing share centres to 0
        for r, v, t in mine:
            X.append([(num(r.get(c)) if num(r.get(c)) is not None else m) - m for c, m in zip(cols, means)])
            y.append(t - ybar); w.append(v); kept.append(r)
    if w:
        mw = sum(w) / len(w)
        w = [min(x / mw, 5.0) for x in w]       # views weights, no single huge day carries the fit
    return X, y, w, kept


def ridge(X, y, w, lam=LAMBDA):
    """Weighted ridge on centred data: (X'WX + lam I) b = X'Wy; None when it cannot be solved."""
    p = len(X[0]) if X else 0
    if not p: return None
    A = [[sum(w[k] * X[k][i] * X[k][j] for k in range(len(X))) + (lam if i == j else 0.0) for j in range(p)] for i in range(p)]
    b = [sum(w[k] * X[k][i] * y[k] for k in range(len(X))) for i in range(p)]
    return solve(A, b)


def fit(rows, factors, boot=BOOT, seed=SEED, lam=LAMBDA):
    """{"n", "channels", "mean_per_1k", "coef": {factor: (coefficient, low, high)}} or {"n": n, "need": m, "coef": {}} when there are
    fewer usable channel-days than MIN_DAYS or PER_FACTOR for each factor with a spread (4 a factor: with 10 days and 9 factors
    every interval is an accident). The interval is the 90% bootstrap over channel-days (seeded)."""
    cols = [c for c in share_cols(factors)]
    X, y, w, kept = design(rows, cols)
    n = len(y)
    if n < MIN_DAYS or not cols: return {"n": n, "need": MIN_DAYS, "coef": {}, "cols": cols}
    # a factor with no spread over these days cannot be told apart from the intercept
    live = [j for j in range(len(cols)) if max(abs(x[j]) for x in X) > 1e-9]
    if not live: return {"n": n, "need": MIN_DAYS, "coef": {}, "cols": cols}
    if n < PER_FACTOR * len(live): return {"n": n, "need": PER_FACTOR * len(live), "coef": {}, "cols": cols}
    X = [[x[j] for j in live] for x in X]; cols = [cols[j] for j in live]
    beta = ridge(X, y, w, lam)
    if beta is None: return {"n": n, "coef": {}, "cols": cols}
    rng = random.Random(seed)
    draws = [[] for _ in cols]
    for _ in range(boot):
        idx = [rng.randrange(n) for _ in range(n)]
        b = ridge([X[i] for i in idx], [y[i] for i in idx], [w[i] for i in idx], lam)
        if b:
            for j, v in enumerate(b): draws[j].append(v)
    coef = {}
    for j, c in enumerate(cols):
        ds = sorted(draws[j])
        lo, hi = (ds[int(0.05 * (len(ds) - 1))], ds[int(math.ceil(0.95 * (len(ds) - 1)))]) if len(ds) >= 20 else (None, None)
        coef[c[len("share_"):]] = (beta[j], lo, hi)
    views = sum(num(r.get("views")) for r in kept)
    return {"n": n, "channels": sorted({r.get("channel") for r in kept}),
            "mean_per_1k": 1000.0 * sum(num(r.get("subs_gained")) for r in kept) / views if views else None, "coef": coef, "cols": cols}


def render_md(res, factors, today=""):
    L = ["# The channel-day subscriber model (advisory only)", "",
         f"Updated {today}. pipeline/subs_daily.py: a ridge regression of subscribers gained per 1,000 views on the day's mix, within "
         "channel, weighted by views, over channel-days with 100 or more views. Nothing reads it yet. YouTube Analytics counts its days "
         "in Pacific time, the Shorts columns are UK days, so a day's subscribers can include the end of the day before.", ""]
    n = res.get("n", 0)
    L.append(f"Channel-days used: {n}" + (f" on {', '.join(res['channels'])}" if res.get("channels") else "") +
             (f"; {res['mean_per_1k']:.2f} subscribers per 1,000 views on average." if res.get("mean_per_1k") is not None else "."))
    if not res.get("coef"):
        L += ["", f"Not enough yet: it needs {res.get('need', MIN_DAYS)} channel-days with 100 or more views and a spread in the mix ({PER_FACTOR} for each factor), "
                  "and has " + str(n) + ". The factors' shares are in analytics/subs_daily.csv."]
        return "\n".join(L) + "\n"
    L += ["", "| factor | arm B against arm A (subscribers per 1,000 views) | 90% interval | clear |", "|---|---|---|---|"]
    for f, (b, lo, hi) in sorted(res["coef"].items(), key=lambda kv: -abs(kv[1][0])):
        a_b = factors.get(f) or ["a", "b"]
        clear = lo is not None and (lo > 0 or hi < 0)
        L.append(f"| {f} ({a_b[1]} against {a_b[0]}) | {b:+.2f} | " + (f"{lo:+.2f} to {hi:+.2f}" if lo is not None else "n/a") + f" | {'yes' if clear else 'no'} |")
    L += ["", "A coefficient is what a day of all arm B adds over a day of all arm A, with the other factors' mix and the channel held fixed. "
          "The ridge pulls every coefficient towards 0, so a small effect reads smaller than it is; days are not independent of each other "
          "(the same topics run over several days), so treat a 'clear' as a lead to test on Shorts, not a verdict."]
    return "\n".join(L) + "\n"


def write(out_dir, rows, daily_by_channel, factors, today=None):
    """Writes subs_daily.csv (merged with the earlier file) and subs_model.md into out_dir; returns the fit."""
    out_dir = pathlib.Path(out_dir)
    cols = BASE + share_cols(factors)
    p = out_dir / "subs_daily.csv"
    try: old = list(csv.DictReader(io.StringIO(p.read_text()))) if p.exists() else []
    except Exception: old = []
    allcols = cols + [c for c in (old[0].keys() if old else []) if c not in cols and c.startswith("share_")]
    merged = merge(old, build(rows, daily_by_channel, factors), allcols)
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=allcols, lineterminator="\n"); w.writeheader(); w.writerows(merged)
    p.write_text(buf.getvalue())
    res = fit(merged, factors)
    (out_dir / "subs_model.md").write_text(render_md(res, factors, today or dt.datetime.now(UK).date().isoformat()))
    return res
