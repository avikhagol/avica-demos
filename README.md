# AVICA Demos

A single-page gallery of asciinema terminal recordings for
[AVICA](https://github.com/avikhagol/avica) — automated VLBI pipeline in CASA.

**Live site:** https://avikhagol.github.io/avica-demos/

Static HTML with no build step. The asciinema player is vendored into `assets/`
so the page has no runtime CDN dependency and keeps working on an unreliable
network — which matters when presenting.

## Layout

```
index.html                     the whole page
demos.json                     manifest — the page renders itself from this
assets/
  asciinema-player.min.js      vendored, v3.8.0
  asciinema-player.css
  style.css
casts/                         the nine .cast recordings
scripts/
  sync_casts.py                regenerates casts/ and demos.json
.nojekyll                      serve files as-is, no Jekyll processing
```

## Updating a demo

Recordings are made from a data directory, not from this repo — see
`demos/README.md` in the main AVICA repository. Once you have re-recorded:

```bash
python3 scripts/sync_casts.py --from /path/to/your/data/casts
git add -A && git commit -m "Update demo recordings" && git push
```

`sync_casts.py` copies the casts in, reads each header for its geometry, and
measures both the raw duration and the idle-compressed playback duration, so
the timings shown on the page can never drift from the actual recordings.

The copy-paste command shown under each demo's player is extracted the same
way: the script decodes what the recording actually printed and picks the one
typed line matching that demo's `COMMAND_PATTERN` in the script. Nothing is
hand-typed, so a real filename or target name from whatever machine recorded
the demo shows up on the page exactly as typed — not a generic placeholder.
Adding a tenth demo means adding a `COMMAND_PATTERN` entry that uniquely
matches the one line you want shown; the script raises loudly if no line in a
recording matches its pattern, rather than silently keeping a stale command.

Run `python3 scripts/sync_casts.py --help` for the options, or `--dry-run` to
preview without writing.

## Adding a tenth demo

Record it, add an entry to `CATALOG` in `scripts/sync_casts.py` keyed by the
cast's filename stem (for example `10_imaging`), then re-run the script. No
HTML needs editing.

## Playback timing

Demos 06 and 08 are real reductions and spend most of their wall-clock time
waiting on CASA — 11m21s and 9m36s respectively. The player compresses idle
gaps longer than one second, which brings those down to about 3m13s and 3m42s
without touching the recordings themselves. Each demo displays its true runtime
next to the playback length, since how long a real reduction takes is itself
worth knowing.

## Sample data

Demos 04–09 need a VLBI FITS-IDI dataset. The sample used in these recordings
is hosted separately (not in this repo, to keep it small):

```bash
curl -L "https://cloud.ia.forth.gr/index.php/s/kiBDyJ7Wg97rtEC/download" -o files.zip && unzip files.zip -d avica_test_data
```

This is also shown on the live page itself, under "What the demos assume."

## Local preview

The page fetches `demos.json` and the casts over HTTP, so opening `index.html`
straight from disk will not work. Serve the folder instead:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/
```

## Keyboard

`1`–`9` jump to a demo, `[` and `]` step through them. The player itself handles
space to pause and arrow keys to seek.

## Acknowledgement

AVICA was developed within the "Search for Milli-Lenses" (SMILE) project, which
has received funding from the European Research Council (ERC) under the HORIZON
ERC Grants 2021 programme, grant agreement No. 101040021.
