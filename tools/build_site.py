"""Build the static archive site and podcast feed into docs/ (served by GitHub Pages).

    python tools/build_site.py --base-url https://indiefeedpoetry.org

Writes docs/episodes.json, docs/feed.xml and copies site/index.html into docs/.
The feed only lists shows whose audio is on the Internet Archive (audio_url),
so podcast apps never get a dead link.
"""
import argparse
import email.utils
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
DOCS = ROOT / "docs"
ARTWORK = "https://static.libsyn.com/p/assets/f/7/a/6/f7a6f36fe4290bce/IFPP_iTunes_Large.png"
SUMMARY = ("The IndieFeed Performance Poetry Channel, 2006-2016. 1,614 shows, 632 poets, "
           "one poem per episode. Hosted by Wess \"Mongo\" Jolley.")


def rfc822(d):
    return email.utils.format_datetime(datetime.strptime(d, "%Y-%m-%d").replace(hour=8, tzinfo=timezone.utc))


def feed_xml(eps, base):
    items = []
    for e in reversed(eps):  # newest first
        if not e.get("audio_url"):
            continue
        img = f'<itunes:image href="{escape(e["image_original"])}"/>' if e.get("image_original") else ""
        dur = f"<itunes:duration>{escape(e['duration'])}</itunes:duration>" if e.get("duration") else ""
        num = f"<itunes:episode>{e['show_number']}</itunes:episode>" if e.get("show_number") else ""
        items.append(f"""<item>
<title>{escape(e['title'])}</title>
<guid isPermaLink="false">{escape(e['id'])}</guid>
<pubDate>{rfc822(e['date'])}</pubDate>
<link>{escape(base)}/#{escape(e['id'])}</link>
<description>{escape(e.get('notes', ''))}</description>
<enclosure url="{escape(e['audio_url'])}" length="{e.get('bytes') or 0}" type="audio/mpeg"/>
{dur}{num}{img}<itunes:episodeType>full</itunes:episodeType>
</item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>IndieFeed: Performance Poetry</title>
<link>{escape(base)}/</link>
<atom:link href="{escape(base)}/feed.xml" rel="self" type="application/rss+xml"/>
<description>{escape(SUMMARY)}</description>
<language>en</language>
<itunes:author>Wess Mongo Jolley</itunes:author>
<itunes:summary>{escape(SUMMARY)}</itunes:summary>
<itunes:image href="{ARTWORK}"/>
<itunes:category text="Arts"><itunes:category text="Books"/></itunes:category>
<itunes:explicit>true</itunes:explicit>
<itunes:type>episodic</itunes:type>
<itunes:complete>Yes</itunes:complete>
{chr(10).join(items)}
</channel>
</rss>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://steps-re.github.io/ifpp-archive")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    eps = [e for e in json.loads(EPISODES.read_text()) if not e.get("removed")]
    slim = [{
        "id": e["id"], "n": e.get("show_number"), "d": e["date"], "poet": e.get("poet") or e["title"],
        "poem": e.get("poem", ""), "notes": e.get("notes", ""), "img": e.get("image_original"),
        "audio": e.get("audio_url") or e.get("wayback_audio_url"),
        "src": "ia" if e.get("audio_url") else ("wayback" if e.get("wayback_audio_url") else None),
    } for e in eps]
    DOCS.mkdir(exist_ok=True)
    (DOCS / "episodes.json").write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")))
    (DOCS / "feed.xml").write_text(feed_xml(eps, base))
    for page in (ROOT / "site").glob("*.html"):
        shutil.copy(page, DOCS / page.name)
    (DOCS / ".nojekyll").write_text("")
    on_ia = sum(1 for e in eps if e.get("audio_url"))
    on_wb = sum(1 for e in eps if not e.get("audio_url") and e.get("wayback_audio_url"))
    print(f"site: {len(slim)} shows | audio on Internet Archive: {on_ia} | Wayback-only audio: {on_wb} "
          f"| feed items: {on_ia}")


if __name__ == "__main__":
    main()
