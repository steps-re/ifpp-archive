"""Upload IFPP MP3s to the Internet Archive, one item per show.

Usage (Mongo runs this, under his own archive.org account):
    pip install -r requirements.txt
    ia configure                      # one-time login to archive.org
    python tools/ia_upload.py /path/to/mp3s            # dry run: shows the match report
    python tools/ia_upload.py /path/to/mp3s --go       # actually uploads
    python tools/ia_upload.py /path/to/mp3s --go --limit 5   # try a few first

Files are matched to episodes by their original Libsyn filename
(e.g. indiefeed_marytaibs_familydysfunctioninthe.mp3). Re-running skips shows
already uploaded, so an interrupted run just picks up where it stopped.
Each upload writes the audio URL back into data/episodes.json.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
COLLECTION = "opensource_audio"  # IA's open community audio collection; any account can upload here
RIGHTS_NOTE = ("Originally published on the IndieFeed Performance Poetry Channel (2006-2016), "
               "hosted by Wess \"Mongo\" Jolley. Rights remain with the poet. "
               "Poets who want a recording removed can contact mongo@wessmongojolley.com.")


def metadata(e):
    return {
        "title": f"IndieFeed Performance Poetry #{e['show_number']}: {e['title']}" if e.get("show_number")
                 else f"IndieFeed Performance Poetry: {e['title']}",
        "creator": e.get("poet") or "IndieFeed Performance Poetry",
        "date": e.get("date"),
        "description": f"{e.get('notes', '')}<br><br>{RIGHTS_NOTE}",
        "subject": ["performance poetry", "spoken word", "slam poetry", "IndieFeed", e.get("poet") or ""],
        "mediatype": "audio",
        "collection": COLLECTION,
        "language": "eng",
        "series": "IndieFeed Performance Poetry Channel",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp3_dir", type=Path)
    ap.add_argument("--go", action="store_true", help="really upload (default is a dry run)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    eps = json.loads(EPISODES.read_text())
    files = {p.name.lower(): p for p in args.mp3_dir.rglob("*.mp3")}
    todo, done, missing = [], 0, []
    for e in eps:
        if e.get("removed"):
            continue
        if e.get("audio_url"):
            done += 1
        elif e.get("mp3_file") in files:
            todo.append((e, files[e["mp3_file"]]))
        else:
            missing.append(e)
    matched = {e["mp3_file"] for e, _ in todo} | {e.get("mp3_file") for e in eps if e.get("audio_url")}
    unmatched = sorted(set(files) - matched)

    print(f"{len(eps)} episodes | {done} already uploaded | {len(todo)} ready | {len(missing)} with no file")
    print(f"{len(files)} mp3s in folder, {len(unmatched)} don't match any known episode")
    (ROOT / "data" / "upload_report.json").write_text(json.dumps({
        "no_file": [e["id"] for e in missing], "unmatched_files": unmatched}, indent=1))
    print("details: data/upload_report.json")
    if not args.go:
        print("dry run only. Add --go to upload.")
        return

    from internetarchive import upload  # imported late so the dry run needs no install
    by_id = {e["id"]: e for e in eps}
    for n, (e, path) in enumerate(todo[: args.limit or None], 1):
        print(f"[{n}/{len(todo)}] {e['id']}")
        resp = upload(e["id"], files={path.name: str(path)}, metadata=metadata(e),
                      retries=5, retries_sleep=30, verbose=False)
        if not all(r.status_code == 200 for r in resp):
            sys.exit(f"upload failed for {e['id']}: {[r.status_code for r in resp]}")
        by_id[e["id"]]["ia_identifier"] = e["id"]
        by_id[e["id"]]["audio_url"] = f"https://archive.org/download/{e['id']}/{path.name}"
        EPISODES.write_text(json.dumps(eps, indent=1, ensure_ascii=False))  # checkpoint each upload
    print("done. Now run: python tools/build_site.py")


if __name__ == "__main__":
    main()
