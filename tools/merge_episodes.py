"""Merge the Wayback scrape with the surviving Libsyn feed into data/episodes.json.

The feed has richer data (duration, file size, poet photo) for the last ~148 shows.
The Wayback month pages cover everything back to 2006. Fields already in
data/episodes.json that we add later (ia_identifier, audio_url) are preserved.
"""
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAYBACK = ROOT / "data" / "episodes_wayback.json"
FEED = ROOT / "cache" / "libsyn_rss.xml"
OUT = ROOT / "data" / "episodes.json"
IT = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
KEEP = ("ia_identifier", "audio_url", "wayback_audio_url", "removed")


def mp3_name(url):
    return url.rsplit("/", 1)[-1].split("?")[0].lower() if url else None


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def iso(date_str):
    for parse in (email.utils.parsedate_to_datetime,
                  lambda s: __import__("datetime").datetime.strptime(s, "%a, %d %B %Y")):
        try:
            return parse(date_str).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
    return None


def clean(s):
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "")
    return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def feed_episodes():
    ch = ET.parse(FEED).getroot().find("channel")
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        title = clean(it.findtext("title"))
        poet, _, poem = title.partition(" - ")
        notes = clean(it.findtext("description"))
        show = re.search(r"Show number\s*#?\s*(\d+)", notes, re.I)
        img = it.find(IT + "image")
        yield {
            "date": iso(it.findtext("pubDate")),
            "title": title,
            "poet": poet.strip() if poem else "",
            "poem": poem.strip(),
            "show_number": int(show.group(1)) if show else None,
            "notes": notes,
            "libsyn_page": it.findtext("link"),
            "mp3_original": enc.get("url").split("?")[0] if enc is not None else None,
            "bytes": int(enc.get("length")) if enc is not None and enc.get("length") else None,
            "duration": it.findtext(IT + "duration"),
            "image_original": img.get("href") if img is not None else None,
            "source": "libsyn_feed",
        }


def main():
    prior = {e["id"]: e for e in json.loads(OUT.read_text())} if OUT.exists() else {}
    merged = {}
    for e in json.loads(WAYBACK.read_text()):
        e["date"] = iso(e["date"])
        key = mp3_name(e["mp3_original"]) or e["libsyn_page"]
        merged.setdefault(key, e)  # duplicates come from overlapping month URL variants
    for e in feed_episodes():
        key = mp3_name(e["mp3_original"]) or e["libsyn_page"]
        base = merged.get(key, {})
        merged[key] = {**base, **{k: v for k, v in e.items() if v not in (None, "")}}

    eps = sorted(merged.values(), key=lambda e: (e["date"] or "", e.get("show_number") or 0))
    for e in eps:
        num = f"{e['show_number']:04d}" if e.get("show_number") else e["date"].replace("-", "")
        e["id"] = f"ifpp-{num}-{slugify(e['title'])}"[:100].rstrip("-")
        e["mp3_file"] = mp3_name(e["mp3_original"])
        e.update({k: v for k, v in prior.get(e["id"], {}).items() if k in KEEP})
    ids = [e["id"] for e in eps]
    assert len(ids) == len(set(ids)), "duplicate ids"
    OUT.write_text(json.dumps(eps, indent=1, ensure_ascii=False))
    numbered = sorted(e["show_number"] for e in eps if e.get("show_number"))
    missing = sorted(set(range(1, 1615)) - set(numbered))
    print(f"{len(eps)} episodes, {len(numbered)} with show numbers, "
          f"{len(missing)} show numbers 1-1614 not found, {sum(1 for e in eps if e['mp3_file'])} with mp3 names")


if __name__ == "__main__":
    main()
