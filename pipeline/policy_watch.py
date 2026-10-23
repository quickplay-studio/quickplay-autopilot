"""YouTube rule and law watch (Charlie, 23 October: adapt to new YouTube rules and legislation without him). Every day it
reads free feeds (the official YouTube blog, YouTube's Creator Insider channel, and news searches about Shorts policy,
the Partner Programme, reused content, AI disclosure, UK online safety and advertising rules), has a free model sort the
new items into "act" (changes what we may post or how we earn), "watch" or "ignore", and:
- appends every act and watch item to docs/POLICY.md (dated, with its link): the record a Claude session reads first;
- opens one GitHub issue a run, "📜 Rule changes to act on (<date>)", listing the act items, so the weekly Claude review (a scheduled
  task) or Charlie's next request changes the pipeline to fit.
Nothing here changes the pipeline by itself: news text never goes into a prompt that writes or posts.

usage: python pipeline/policy_watch.py        (report.yml runs it daily at 07:41 UTC)
"""
import datetime as dt, json, pathlib, re, subprocess, sys, xml.etree.ElementTree as ET
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
SEEN = ROOT / "status" / "policy" / "seen.json"      # not status/*.json: those are read as Short status files
LOG = ROOT / "docs" / "POLICY.md"
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
GN = "https://news.google.com/rss/search?q={q}&hl=en-GB&gl=GB&ceid=GB:en"
FEEDS = [("YouTube blog", "https://blog.youtube/rss/"),
         ("Creator Insider", "https://www.youtube.com/feeds/videos.xml?channel_id=UCGg-UqjRgzhYDPJMr-9HXCg")] + [
    (f"News: {q}", GN.format(q=requests.utils.quote(q))) for q in (
        "YouTube Shorts policy update", "YouTube Partner Program requirements change", "YouTube reused content policy",
        "YouTube AI generated content disclosure", "YouTube Shorts algorithm change", "Instagram Reels reposted content reach",
        "Ofcom Online Safety Act video platforms creators", "ASA influencer advertising rules UK", "clipping campaigns Whop rules")]
SORT = """You watch platform rules for a small, anonymous, family-friendly UK YouTube Shorts channel. It posts news and
evergreen Shorts written by AI with an AI voice (Quickplay Daily), and clips of other creators' streams under paid
clipping campaigns (Content Rewards, Vyro) on YouTube, Instagram and Facebook. It wants to reach the Partner Programme
(1,000 subscribers, 10 million Shorts views in 90 days) and earn from campaigns.
For each item below, decide: "act" when it changes what this channel may post, how its Shorts or clips are reached or
recommended, how it can earn, or what UK law requires of it; "watch" when it might soon; else "ignore". Be strict: most
items are "ignore". For act and watch, "note": one plain sentence on what it means for this channel, UK English, no dashes.
Return {"items": [{"n": <number>, "level": "act|watch|ignore", "note": "..."}]}

ITEMS
"""


def items():
    out = []
    for source, url in FEEDS:
        try:
            x = ET.fromstring(requests.get(url, headers=UA, timeout=30).content)
        except Exception as e:
            print(f"{source}: not read ({str(e)[:80]})"); continue
        for it in x.iter():
            tag = it.tag.split("}")[-1]
            if tag not in ("item", "entry"): continue
            title = (it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not link:
                el = it.find("{http://www.w3.org/2005/Atom}link"); link = el.get("href", "") if el is not None else ""
            when = (it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()
            if title and link: out.append({"source": source, "title": title[:200], "link": link, "when": when[:40]})
    return out


def recent(when, days=14):
    """True for an item dated in the last `days` days (or undated)."""
    from email.utils import parsedate_to_datetime
    if not when: return True
    try: t = parsedate_to_datetime(when)
    except Exception:
        try: t = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
        except Exception: return True
    if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t).days <= days


def run():
    try: seen = set(json.loads(SEEN.read_text()))
    except Exception: seen = set()
    fresh = [i for i in items() if i["link"] not in seen]
    new = [i for i in fresh if recent(i["when"])][:60]          # old news was handled already (the first run opened 23 issues)
    print(f"policy watch: {len(new)} new items")
    if not new: return []
    import factpack
    listing = "\n".join(f"{k}. [{i['source']}] {i['title']} ({i['when']})" for k, i in enumerate(new, 1))
    try: ans, model = factpack.gemini(SORT + listing, None, timeout=120, lite=True)
    except Exception as e:
        print("policy watch: no model answered:", str(e)[:120]); return []      # unseen items stay unseen: tried again tomorrow
    picked = []
    for a in (ans.get("items") if isinstance(ans, dict) else None) or []:
        try: i = new[int(a.get("n")) - 1]
        except (TypeError, ValueError, IndexError): continue
        lvl = str(a.get("level") or "").lower()
        if lvl in ("act", "watch"):
            picked.append({**i, "level": lvl, "note": factpack.undash(str(a.get("note") or ""))[:300]})
    today = dt.date.today().isoformat()
    if picked:
        if not LOG.exists():
            LOG.write_text("# Rule and law watch\n\nWritten by pipeline/policy_watch.py: platform rule and UK law items that matter "
                           "to the channel, newest at the bottom. \"act\" items also open a GitHub issue.\n")
        with LOG.open("a") as f:
            for p in picked: f.write(f"- {today} [{p['level']}] {p['note']} ({p['source']}: [{p['title']}]({p['link']}))\n")
    acts = [p for p in picked if p["level"] == "act"]
    if acts:                                   # one issue a run, listing every act item (never one issue per article)
        title = f"📜 Rule changes to act on ({today})"
        subprocess.run(["gh", "label", "create", "policy", "--color", "5319E7", "--description", "A platform rule or law change"],
                       capture_output=True)
        body = "\n".join(f"- {p['note']} ({p['source']}: [{p['title'][:100]}]({p['link']}))" for p in acts)
        r = subprocess.run(["gh", "issue", "create", "--title", title, "--label", "policy", "--body",
                            body + "\n\nThe weekly Claude review reads docs/POLICY.md and these issues and changes the pipeline to "
                            "fit; it closes this once handled."], capture_output=True, text=True)
        print("issue:", title, (r.stdout or r.stderr).strip()[:120])
    SEEN.write_text(json.dumps(sorted(seen | {i["link"] for i in fresh})[-3000:]))
    print(f"policy watch: {sum(p['level'] == 'act' for p in picked)} act, {sum(p['level'] == 'watch' for p in picked)} watch ({model})")
    return picked


if __name__ == "__main__":
    run()
