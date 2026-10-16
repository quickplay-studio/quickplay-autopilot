"""Daily trend shortlist for the script writer, from free sources. Writes trends/latest.json and trends/<date>.json.

Sources: Google Trends daily searches (GB, US), YouTube's most-popular charts (GB, US; all and gaming),
English Wikipedia's most-read pages yesterday, and this channel's own last-7-days performance.
Kept small on purpose: titles and numbers only, so reading it costs Claude very little.
"""
import datetime as dt, json, os, pathlib, re, sys, xml.etree.ElementTree as ET
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
SKIP = re.compile(r"\b(election|vote|minister|president|senate|war|shooting|murder|killed|police|court|trial|arrest|"
                  r"cancer|vaccine|crypto|bitcoin|stock|shares|betting|odds|casino|lottery|porn|onlyfans)\b", re.I)

def google_trends(geo):
    try:
        x = ET.fromstring(requests.get(f"https://trends.google.com/trending/rss?geo={geo}", headers=UA, timeout=30).content)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        out = []
        for it in x.iter("item"):
            title = it.findtext("title", "")
            out.append({"q": title, "traffic": it.findtext("ht:approx_traffic", "", ns),
                        "news": [n.findtext("ht:news_item_title", "", ns) for n in it.findall("ht:news_item", ns)][:2]})
        return [o for o in out if not SKIP.search(o["q"] + " " + " ".join(o["news"]))][:25]
    except Exception as e:
        return [{"error": str(e)[:200]}]

def youtube_charts(yt):
    out = {}
    now = dt.datetime.now(dt.timezone.utc)
    for region in ("GB", "US"):
        for cat in ("", "20"):
            kw = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": 25}
            if cat: kw["videoCategoryId"] = cat
            try: items = yt.videos().list(**kw).execute()["items"]
            except Exception as e: out[f"{region}{'-gaming' if cat else ''}"] = [{"error": str(e)[:200]}]; continue
            rows = []
            for v in items:
                hrs = max(1, (now - dt.datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 3600)
                views = int(v["statistics"].get("viewCount", 0))
                t = v["snippet"]["title"]
                if SKIP.search(t): continue
                rows.append({"title": t, "channel": v["snippet"]["channelTitle"], "views": views, "views_per_hour": round(views / hrs)})
            out[f"{region}{'-gaming' if cat else ''}"] = sorted(rows, key=lambda r: -r["views_per_hour"])[:15]
    return out

def wikipedia_top():
    d = dt.date.today() - dt.timedelta(days=1)
    try:
        arts = requests.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{d:%Y/%m/%d}",
                            headers=UA, timeout=30).json()["items"][0]["articles"]
    except Exception as e:
        return [{"error": str(e)[:200]}]
    junk = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "File:", "Help:")
    return [{"page": a["article"].replace("_", " "), "views": a["views"]} for a in arts
            if not a["article"].startswith(junk) and not SKIP.search(a["article"].replace("_", " "))][:30]

def own_channel():
    import youtube as Y
    from googleapiclient.discovery import build
    try:
        ya = build("youtubeAnalytics", "v2", credentials=Y.creds(), cache_discovery=False)
        end = dt.date.today(); start = end - dt.timedelta(days=7)
        r = ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), dimensions="video",
                               metrics="views,averageViewPercentage,subscribersGained", sort="-views", maxResults=25).execute()
        ids = [row[0] for row in r.get("rows", [])]
        titles = {}
        if ids:
            for v in Y.client().videos().list(part="snippet", id=",".join(ids)).execute()["items"]:
                titles[v["id"]] = v["snippet"]["title"]
        return [{"title": titles.get(row[0], row[0]), "views": row[1], "avg_viewed_pct": round(row[2]), "subs": row[3]} for row in r.get("rows", [])]
    except Exception as e:
        return [{"error": str(e)[:200]}]

def main():
    import youtube as Y
    data = {"date": str(dt.date.today()), "google_trends": {g: google_trends(g) for g in ("GB", "US")},
            "wikipedia_top": wikipedia_top()}
    if Y.available():
        data["youtube_charts"] = youtube_charts(Y.client())
        data["our_last_7_days"] = own_channel()
    d = ROOT / "trends"; d.mkdir(exist_ok=True)
    txt = json.dumps(data, indent=1, ensure_ascii=False)
    (d / "latest.json").write_text(txt); (d / f"{data['date']}.json").write_text(txt)
    print("trends written", len(txt), "bytes")

if __name__ == "__main__":
    main()
