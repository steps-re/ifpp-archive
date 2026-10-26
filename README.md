# IndieFeed Performance Poetry archive

Rebuilds the IFPP Channel (2006-2016, 1,614 shows) as a static site + podcast feed, with audio hosted free on the Internet Archive.

1. `python tools/scrape_wayback.py` rebuilds the show list from Wayback copies of the old Libsyn month pages.
2. `python tools/merge_episodes.py` merges in the surviving Libsyn feed, writes `data/episodes.json`.
3. `python tools/ia_upload.py /path/to/mp3s` matches MP3s to shows (dry run). Add `--go` to upload, one archive.org item per show.
4. `python tools/build_site.py --base-url https://<domain>` writes `docs/` (site, `episodes.json`, `feed.xml`) for GitHub Pages.

Recordings belong to the poets. Set `"removed": true` on a show in `data/episodes.json` to take it down, then rebuild.
