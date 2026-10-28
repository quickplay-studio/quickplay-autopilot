"""False-winner control (28 October): a p-value for each comparison a verdict pass makes, and Benjamini-Hochberg across the pass.

Every interval in drivers.py is a t interval (the group's mean log rel, or a regression slope, against its standard error, t
quantile at its degrees of freedom), so the p-value here is that same t test, two-sided: p = P(|T| >= |estimate / se|) at
the same degrees of freedom. A winner or push is only called when the interval is clear AND its Benjamini-Hochberg q-value
across all the comparisons of that pass is at or under analysis.fdr_q (config, default 0.10): with 13 live contests and about
100 groups in drivers.csv, one of them clears a 90% interval by luck most days, and this is the check for it.

Standard library only (the analytics workflow installs nothing for it). Also holds the settings of the two analysis rules
that share the config block "analysis": fdr_q, confirm_share and confirm_n (evolve.py's confirmation of an adopted winner)."""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULTS = {"fdr_q": 0.10, "confirm_share": 0.2, "confirm_n": 20}


def settings(cfg=None):
    """config.json's "analysis" block over DEFAULTS; `cfg` is a loaded config (None: read the repo's config.json)."""
    if cfg is None:
        try: cfg = json.loads((ROOT / "config.json").read_text())
        except Exception: cfg = {}
    out = dict(DEFAULTS)
    for k, v in ((cfg or {}).get("analysis") or {}).items():
        if k in DEFAULTS and isinstance(v, (int, float)) and not isinstance(v, bool): out[k] = v
    out["fdr_q"] = min(1.0, max(1e-6, float(out["fdr_q"])))
    out["confirm_share"] = min(0.5, max(0.0, float(out["confirm_share"])))
    out["confirm_n"] = max(0, int(out["confirm_n"]))
    return out


def _betacf(a, b, x):
    """Continued fraction of the incomplete beta function (modified Lentz)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = d if abs(d) > tiny else tiny
        c = 1.0 + aa / c; c = c if abs(c) > tiny else tiny
        d = 1.0 / d; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = d if abs(d) > tiny else tiny
        c = 1.0 + aa / c; c = c if abs(c) > tiny else tiny
        d = 1.0 / d; delta = d * c; h *= delta
        if abs(delta - 1.0) < 3e-16: break
    return h


def betai(a, b, x):
    """The regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0: return 0.0
    if x >= 1.0: return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0): return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_p(t, df):
    """Two-sided p-value of a t statistic at df degrees of freedom (the test behind drivers.interval and the round's slopes);
    None without a usable statistic."""
    try: t, df = float(t), float(df)
    except (TypeError, ValueError): return None
    if df <= 0 or math.isnan(t) or math.isinf(t): return None
    if df > 1e6: return math.erfc(abs(t) / math.sqrt(2.0))
    return min(1.0, max(0.0, betai(df / 2.0, 0.5, df / (df + t * t))))


def normal_p(z):
    """Two-sided p-value of a standard normal statistic (for the intervals made with 1.645)."""
    try: return math.erfc(abs(float(z)) / math.sqrt(2.0))
    except (TypeError, ValueError): return None


def mean_p(logs):
    """Two-sided p-value of a one-sample t test of the mean of `logs` against 0 (drivers.interval's own test: the group's mean
    log rel against typical), or None under 2 values or with no spread."""
    n = len(logs)
    if n < 2: return None
    m = sum(logs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in logs) / (n - 1))
    if sd <= 1e-12: return 0.0 if abs(m) > 1e-12 else 1.0
    return t_p(m / (sd / math.sqrt(n)), n - 1)


def bh(ps):
    """Benjamini-Hochberg adjusted p-values (q-values) for a list of p-values, in the same order; a None stays None and is not
    counted. A comparison passes at false discovery rate q when its adjusted value is at or under q."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    order = sorted(idx, key=lambda i: ps[i])
    out, prev = [None] * len(ps), 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, ps[i] * m / rank)
        out[i] = prev
    return out


def luck_note(p, q, m, fdr_q):
    """The sentence that goes with a comparison the check withheld."""
    return f"luck check: p {p:.3f}, adjusted q {q:.2f} is over {fdr_q:.2f} among {m} comparisons"
