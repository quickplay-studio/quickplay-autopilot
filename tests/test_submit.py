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
rows = [row(), row(submitted="2026-10-21 18:05"), row(submitted="failed: no answer"), row(submitted="failed: past the 30-minute window"), row(public_at_uk="private test"),
        row(public_at_uk=(uk + dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")), row(public_at_uk=(uk - dt.timedelta(days=4)).strftime("%Y-%m-%d %H:%M")),
        row(platform="tiktok", video="TikTok: open the app")]
d = S.due(rows)
assert len(d) == 2 and d[1]["submitted"].startswith("failed"), d
assert len(S.due(rows, lambda url: False)) == 0 and len(S.due(rows, lambda url: True)) == 2
print("2 due rows ok")

# 3. the browser steps on local pages shaped like the real forms (22 October): Content Rewards' dialog (a url box, three
# checks, a consent checkbox, Submit clip; a Failed icon beside the reason when a check fails, the dialog closing on
# success) and Vyro's Add Posts cards (Submit post per card, Use a link instead, the rules checkbox, Continue, Review
# your post, Submit post, then the answer)
page_ok = SCRATCH / "campaign.html"
page_ok.write_text("""<html><body><h1>$8,000 Speed x Expedia</h1><p>Clips must be 15 to 55 seconds and cannot show other brands.</p>
<button onclick="document.getElementById('d').style.display='block'">Submit clip</button>
<div id="d" role="dialog" style="display:none"><h2>Submit clip link</h2>
<input id="u" type="url" placeholder="https://www.tiktok.com/@username/video...">
<div><span>Posted from one of your linked accounts</span><p>We match the clip's author against the social accounts connected to your profile.</p></div>
<div><span>Not already submitted to any campaign</span><p>A clip can only earn once, in one campaign.</p></div>
<div id="w"><span>Posted within the last 30 minutes</span><p id="wp">This campaign only accepts freshly posted clips, so views are counted from zero.</p></div>
<label><input id="c" type="checkbox"> I've read the requirements and accept that non-compliant clips may be auto-rejected.</label>
<button onclick="document.getElementById('d').style.display='none'">Cancel</button><button onclick="go()">Submit clip</button></div>
<script>function go(){var u=document.getElementById('u').value;if(!document.getElementById('c').checked)return;
 if(u.indexOf('old')>=0){document.getElementById('wp').textContent='Posts have to be submitted within 30 minutes of going live, and this one is past that window.';
   var i=document.createElement('img');i.alt='Failed';i.src='x';document.getElementById('w').appendChild(i);}
 else if(u.indexOf('youtube.com')>=0){document.getElementById('d').style.display='none';}
 else {document.getElementById('wp').textContent='That link is invalid for this campaign.';var i=document.createElement('img');i.alt='Failed';i.src='x';document.getElementById('w').appendChild(i);}}</script></body></html>""")
page_vyro = SCRATCH / "vyro.html"
page_vyro.write_text("""<html><body><h1>My campaigns</h1>
<section><h3>Kizik</h3><p>MrBeast x Kizik Shoes Integration</p><span>Locked for new posts</span><button disabled>Submit post</button></section>
<section><h3>Call of Duty: Modern Warfare 4</h3><p>MrBeast Gaming: Escape Call of Duty's DMZ, Win $1,000,000</p><button onclick="open1()">Submit post</button></section>
<div id="d1" role="dialog" style="display:none"><h2>Submit post</h2><label>Campaign</label><button role="combobox">Call of Duty: Modern Warfare 4</button>
<label>Social account</label><button role="combobox" id="sa" onclick="document.getElementById('opts').style.display='block'">Select social account</button>
<div id="opts" style="display:none"><div role="option" onclick="pick()">Connect a social account</div><div role="option" onclick="pick()">quickplayclips-x9b YouTube</div></div>
<span id="left" style="display:none">This account can submit 5 posts today.</span>
<button id="ul" onclick="document.getElementById('lf').style.display='block'">Use a link instead</button>
<div id="lf" style="display:none"><label>Link your social post</label><input id="pl" placeholder="Paste link"></div>
<label>My post follows campaign rules</label><button id="cb" role="checkbox" aria-checked="false" onclick="this.setAttribute('aria-checked','true');document.getElementById('ct').disabled=false"></button>
<button id="ct" disabled onclick="review()">Continue</button></div>
<div id="d2" role="dialog" style="display:none"><h2>Review your post</h2><p>Hashtags look good</p><button onclick="finish()">Submit post</button><button>Back</button></div>
<div id="d3" role="dialog" style="display:none"><h3 id="t"></h3><p id="m"></p><button onclick="document.getElementById('d3').style.display='none'">Ok</button></div>
<script>function open1(){document.getElementById('d1').style.display='block'}
function pick(){document.getElementById('opts').style.display='none';document.getElementById('sa').textContent='quickplayclips-x9b YouTube';document.getElementById('left').style.display='inline'}
function review(){document.getElementById('d1').style.display='none';document.getElementById('d2').style.display='block'}
function finish(){document.getElementById('d2').style.display='none';var u=document.getElementById('pl').value;var d=document.getElementById('d3');d.style.display='block';
 if(u.indexOf('dup')>=0){document.getElementById('t').textContent='Post not submitted';document.getElementById('m').textContent='You have already submitted this post to a campaign.';}
 else {document.getElementById('t').textContent='Post submitted';document.getElementById('m').textContent='Your post is pending review.';}}</script></body></html>""")
page_out = SCRATCH / "out.html"
page_out.write_text("<html><body><h1>Content Rewards</h1><a href='/login'>Log in</a><button>Sign up</button></body></html>")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as play:
        b = play.chromium.launch(); page = b.new_context().new_page()
        r = {"campaign_url": page_ok.as_uri(), "platform": "youtube", "video": "https://youtube.com/shorts/abc", "clip": "t-1"}
        assert S.submit_cr(page, r, {}) == "submitted"
        assert S.submit_cr(page, r, {}, dry=True).startswith("dry: logged in")
        old = dict(r, video="https://youtube.com/shorts/old")
        res = S.submit_cr(page, old, {}); assert res.startswith("failed: past the 30-minute window"), res
        bad = dict(r, video="https://vimeo.com/1")
        res = S.submit_cr(page, bad, {}); assert res.startswith("failed:") and "invalid" in res, res
        page.goto(page_out.as_uri()); assert S.logged_out(page)
        try: S.submit_cr(page, dict(r, campaign_url=page_out.as_uri()), {}); raise AssertionError("no Stale")
        except S.Stale: pass
        S.VYRO_ADD = page_vyro.as_uri()
        c = {"card": "MrBeast Gaming: Escape Call of Duty's DMZ, Win $1,000,000", "name": "MrBeast Gaming: Escape Call of Duty's DMZ, Win $1,000,000 (Call of Duty MW4)", "subject": "MrBeast"}
        v = {"platform": "youtube", "video": "https://youtube.com/shorts/abc", "clip": "v-1", "channel": "clips"}
        assert S.submit_vyro(page, v, c) == "submitted"
        assert S.submit_vyro(page, dict(v, video="https://youtube.com/shorts/dup"), c) == "already"
        res = S.submit_vyro(page, v, {"card": "MrBeast x Kizik Shoes Integration", "subject": "Kizik"}); assert "locked" in res, res
        res = S.submit_vyro(page, v, {"card": "No such campaign", "subject": "Nobody"}); assert res.startswith("failed: campaign"), res
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
