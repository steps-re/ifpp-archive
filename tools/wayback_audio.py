"""Find which IFPP MP3s the Wayback Machine saved, and mark them in data/episodes.json.

This is a fallback for shows whose original file is lost. The site plays these
(labelled "from the Wayback Machine") until the Internet Archive upload replaces them.
Also writes data/wayback_audio.csv so the files can be downloaded and re-uploaded properly.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
CACHE = ROOT / "cache" / "wayback_mp3_cdx.txt"
UA = "ifpp-archive-rebuild/0.1 (personal preservation project)"
PREFIXES = ["traffic.libsyn.com/indiefeedpp/", "traffic.libsyn.com/secure/indiefeedpp/",
            "media.libsyn.com/media/indiefeedpp/", "indiefeedpp.libsyn.com/media/"]


def cdx(prefix):
    q = urllib.parse.urlencode({"url": prefix, "matchType": "prefix", "filter": "statuscode:200",
                                "fl": "original,timestamp,mimetype,length", "collapse": "urlkey", "limit": 50000})
    for i in range(4):
        try:
            req = urllib.request.Request(f"https://web.archive.org/cdx/search/cdx?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read().decode()
        except Exception as e:
            print(f"  {prefix}: retry {i + 1} after {e!r}")
            time.sleep(30 * (i + 1))
    return ""


def main():
    if not CACHE.exists():
        CACHE.write_text("\n".join(cdx(p) for p in PREFIXES))
    found = {}
    for line in CACHE.read_text().splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].lower().split("?")[0].endswith(".mp3"):
            continue
        if parts[3].isdigit() and int(parts[3]) < 100_000:  # tiny captures are error pages, not audio
            continue
        name = parts[0].rsplit("/", 1)[-1].split("?")[0].lower()
        found.setdefault(name, f"https://web.archive.org/web/{parts[1]}id_/{parts[0]}")
    eps = json.loads(EPISODES.read_text())
    hits = 0
    for e in eps:
        if e.get("mp3_file") in found:
            e["wayback_audio_url"] = found[e["mp3_file"]]
            hits += 1
    EPISODES.write_text(json.dumps(eps, indent=1, ensure_ascii=False))
    (ROOT / "data" / "wayback_audio.csv").write_text(
        "id,mp3_file,wayback_url\n" + "".join(
            f"{e['id']},{e['mp3_file']},{e['wayback_audio_url']}\n" for e in eps if e.get("wayback_audio_url")))
    print(f"Wayback has audio for {hits} of {len(eps)} shows ({len(found)} distinct mp3 captures)")


if __name__ == "__main__":
    main()
