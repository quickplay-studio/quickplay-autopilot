"""Offline test of the submissions (pipeline/submit.py): cookie files, which rows are due, and the browser steps against
two local pages that behave like a campaign page (a Submit clip button, a dialog with a link box, a Submit button, an
answer) and a logged-out page. Playwright's Chromium is needed for the last part; without it that part is skipped."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, os, re, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import submit as S

# 1. cookies: a cookies.txt export (with #HttpOnly_ lines) and a JSON export
txt = ("# Netscape HTTP Cookie File\n.contentrewards.com\tTRUE\t/\tTRUE\t1790000000\tsession\tabc\n"
       "#HttpOnly_.whop.com\tTRUE\t/\tTRUE\t0\twhop_sid\txyz\napp.vyro.com\tFALSE\t/\tFALSE\t1790000000\tvyro\t123\n")
cs = S.cookies(txt)
assert len(cs) == 3 and cs[0]["domain"] == ".contentrewards.com" and cs[0]["secure"] and cs[0]["expires"] == 1790000000.0
assert cs[1]["httpOnly"] and cs[1]["expires"] == -1 and cs[1]["name"] == "whop_sid"
js = S.cookies('[{"name": "a", "value": "1", "domain": ".whop.com", "path": "/", "expirationDate": 1790000000.5, "sameSite": "no_restriction", "secure": true}]')
assert js[0]["sameSite"] == "None" and js[0]["expires"] == 1790000000.5
os.environ["WHOP_COOKIES"] = txt; os.environ["VYRO_COOKIES"] = txt
assert {c["name"] for c in S.site_cookies("Content Rewards")} == {"session", "whop_sid"} and [c["name"] for c in S.site_cookies("Vyro")] == ["vyro"]
assert S.site_of({"platform": "Vyro"}) == "Vyro" and S.site_of({"platform": "Content Rewards (Reach)"}) == "Content Rewards"
print("1 cookies ok")

# 2. due rows: public already, with a link, not submitted (a failed one is tried again), under 3 days old
uk = S.NOW.astimezone(S.UK)
row = lambda **k: {"clip": "x", "campaign": "speed-expedia", "platform": "youtube", "video": "https://youtube.com/shorts/abc", "public_at_uk": (uk - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), "submitted": "", **k}
rows = [row(), row(submitted="2026-10-21 18:05"), row(submitted="failed: no answer"), row(public_at_uk="private test"),
        row(public_at_uk=(uk + dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")), row(public_at_uk=(uk - dt.timedelta(days=4)).strftime("%Y-%m-%d %H:%M")),
        row(platform="tiktok", video="TikTok: open the app")]
d = S.due(rows)
assert len(d) == 2 and d[1]["submitted"].startswith("failed"), d
assert len(S.due(rows, lambda url: False)) == 0 and len(S.due(rows, lambda url: True)) == 2
print("2 due rows ok")

# 3. the browser steps on local pages
page_ok = SCRATCH / "campaign.html"
page_ok.write_text("""<html><body><h1>$8,000 Speed x Expedia</h1><p>Clips must be 15 to 55 seconds and cannot show other brands.</p>
<button onclick="document.getElementById('d').style.display='block'">Submit clip</button>
<div id="d" role="dialog" style="display:none"><label>Platform</label>
<label><input type="radio" name="p" value="yt"> YouTube</label><label><input type="radio" name="p" value="ig"> Instagram</label>
<input id="u" type="text" placeholder="Paste your clip link"><button onclick="go()">Submit</button><p id="a"></p></div>
<script>function go(){var u=document.getElementById('u').value;document.getElementById('a').textContent=
 u.indexOf('youtube.com')>=0?'Submitted! Your clip is pending review.':'That link is invalid';}</script></body></html>""")
page_out = SCRATCH / "out.html"
page_out.write_text("<html><body><h1>Content Rewards</h1><a href='/login'>Log in</a><button>Sign up</button></body></html>")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as play:
        b = play.chromium.launch(); page = b.new_context().new_page()
        r = {"campaign_url": page_ok.as_uri(), "platform": "youtube", "video": "https://youtube.com/shorts/abc", "clip": "t-1"}
        assert S.submit_cr(page, r, {}) == "submitted"
        assert S.submit_cr(page, r, {}, dry=True).startswith("dry: logged in")
        bad = dict(r, video="https://vimeo.com/1")
        res = S.submit_cr(page, bad, {}); assert res.startswith("failed:") and "invalid" in res, res
        page.goto(page_out.as_uri()); assert S.logged_out(page)
        try: S.submit_cr(page, dict(r, campaign_url=page_out.as_uri()), {}); raise AssertionError("no Stale")
        except S.Stale: pass
        b.close()
    print("3 browser steps ok")
except ImportError:
    print("3 browser steps skipped (no playwright)")
print("submit ok")

# 4. the scout's heat: today's trend data and our viewers' searches, no network needed for those two signals
import json as _json, pathlib as _pl
root = _pl.Path(SCRATCH) / "root"; (root / "trends").mkdir(parents=True); (root / "analytics").mkdir()
(root / "trends" / "latest.json").write_text(_json.dumps({"google_trends": {"GB": [{"q": "Test Subject tour", "news": ["Test Subject announces dates"]}]},
                                                          "wikipedia_top": [{"page": "Other"}], "youtube_charts": {}}))
(root / "analytics" / "search_terms.csv").write_text("term,views\ntest subject live,40\n")
S.ROOT = root
import clips as _C; _C.searches = lambda subject, n=8: []
import requests as _rq; _rq.get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
score, why = S.heat("Test Subject")
assert score == 1.1 and "in Google Trends today" in why and any("our viewers search" in w for w in why), (score, why)
assert S.heat("")[0] == 0.0
print("4 heat ok")
