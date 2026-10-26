"""Rebuild the IFPP episode list from Wayback Machine copies of the old Libsyn month pages.

Fetches one month page at a time (polite pace), caches raw HTML in cache/pages/,
and writes data/episodes.json. Safe to re-run: cached pages are not re-fetched.
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "pages"
CDX = ROOT / "cache" / "wayback_libsyn_cdx.txt"
OUT = ROOT / "data" / "episodes_wayback.json"
LOCK = ROOT / "cache" / "scrape.lock"
CDX_URL = ("https://web.archive.org/cdx/search/cdx?url=indiefeedpp.libsyn.com&matchType=domain"
           "&fl=original,mimetype,statuscode,timestamp&collapse=urlkey&limit=50000")
UA = "ifpp-archive-rebuild/0.1 (personal preservation project)"
DELAY_S = 5
OLD_TEMPLATE_UNTIL = "2017"

MONTH_RE = re.compile(r"^https?://(?:www\.)?indiefeedpp\.libsyn\.com(?::80)?/(?:webpage/)?(20\d\d)/(\d\d)(/\d+)?/?$")
TITLE_RE = re.compile(r"<a class=\"postTitle\" href=['\"]([^'\"]+)['\"]>(.*?)</a>", re.S)
MP3_RE = re.compile(r"href=['\"](https?://(?:traffic|media)\.libsyn\.com/[^'\"]+\.mp3)[^'\"]*['\"]", re.I)
BOILER_RE = re.compile(r"Contact Mongo|Subscribe to our feed|Check out The IndieFeed|1-click|feedburner|"
                       r"^\s*Direct download|^Category:|posted at:", re.I)
SHOW_RE = re.compile(r"Show number\s*#?\s*(\d+)", re.I)


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # Wayback 5xx/timeouts are routine; back off and retry
            wait = 30 * (i + 1)
            print(f"  retry {i + 1} after {e!r}, sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {url}")


def snapshots():
    """Month pages and day pages per month, as (url, timestamp), best first.

    Libsyn switched to a JavaScript-rendered template around 2017, so only captures
    before OLD_TEMPLATE_UNTIL hold the episode list in the HTML. Among those, the
    latest capture is best because it was taken after all of that month's posts existed.
    """
    if not CDX.exists():
        CDX.parent.mkdir(parents=True, exist_ok=True)
        CDX.write_text(get(CDX_URL))
    months, days = {}, {}
    for line in CDX.read_text().splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[2] != "200" or parts[3] >= OLD_TEMPLATE_UNTIL:
            continue
        m = MONTH_RE.match(parts[0])
        if not m:
            continue
        key = f"{m.group(1)}-{m.group(2)}"
        bucket = days.setdefault(key, {}) if m.group(3) else months.setdefault(key, [])
        if m.group(3):
            day = int(m.group(3).strip("/"))
            if day not in bucket or parts[3] > bucket[day][1]:
                bucket[day] = (parts[0], parts[3])
        else:
            bucket.append((parts[0], parts[3]))
    for v in months.values():
        v.sort(key=lambda s: s[1], reverse=True)
    return months, days


def fetch(name, url, ts):
    f = CACHE / f"{name}.html"
    if not f.exists():
        f.write_text(get(f"https://web.archive.org/web/{ts}id_/{url}"))
        time.sleep(DELAY_S)
    return f.read_text()


def clean(s):
    s = re.sub(r"<br\s*/?>|</p>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


def parse(page_html, month):
    # Libsyn's template changed over the years, so split on each post's date div and
    # pull fields out of the chunk rather than matching one exact layout.
    eps = []
    chunks = re.split(r'<div class="postDate">', page_html)[1:]
    for chunk in chunks:
        chunk = chunk.split('class="postSeparator"')[0]
        date = clean(chunk.split("</div>", 1)[0])
        t = TITLE_RE.search(chunk)
        if not t:
            continue
        title = clean(t.group(2))
        poet, _, poem = title.partition(" - ")
        body_m = re.search(r'<div class="postBody">(.*?)<div class="postDetails">', chunk, re.S)
        body = clean(body_m.group(1)) if body_m else ""
        notes = "\n".join(l for l in body.splitlines() if l.strip() and not BOILER_RE.search(l))
        mp3 = MP3_RE.search(chunk)
        show = SHOW_RE.search(body)
        img = re.search(r'src ?="(https?://assets\.libsyn\.com/content/\d+)"', chunk)
        page = t.group(1)
        if page.startswith("/"):
            page = "https://indiefeedpp.libsyn.com" + page
        eps.append({
            "date": date,
            "title": title,
            "poet": poet.strip() if poem else "",
            "poem": poem.strip(),
            "show_number": int(show.group(1)) if show else None,
            "notes": notes,
            "libsyn_page": page.replace("http://", "https://"),
            "mp3_original": mp3.group(1) if mp3 else None,
            "image_original": img.group(1) if img else None,
            "source": f"wayback:{month}",
        })
    return eps


def main():
    if LOCK.exists():
        sys.exit(f"lock held: {LOCK} (another scrape running?)")
    CACHE.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(str(os.getpid()))
    try:
        months, days = snapshots()
        print(f"{len(months)} months with old-template captures")
        all_eps = []
        for month in sorted(set(months) | set(days)):
            eps = []
            for i, (url, ts) in enumerate(months.get(month, [])[:3]):
                eps = parse(fetch(f"{month}" if i == 0 else f"{month}_{ts}", url, ts), month)
                if eps:
                    break
            # A month page captured mid-month misses later posts; fill gaps from day pages.
            have = {int(e["date"].split()[1]) for e in eps if e["date"].split()[1:2] and e["date"].split()[1].isdigit()}
            extra = 0
            for day, (url, ts) in sorted(days.get(month, {}).items()):
                if day in have:
                    continue
                got = parse(fetch(f"{month}-{day:02d}", url, ts), month)
                eps.extend(got)
                extra += len(got)
            print(f"{month}: {len(eps)} episodes ({extra} from day pages)")
            all_eps.extend(eps)
        OUT.write_text(json.dumps(all_eps, indent=1, ensure_ascii=False))
        print(f"wrote {len(all_eps)} episodes to {OUT}")
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
