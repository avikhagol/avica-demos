#!/usr/bin/env python3
"""Sync AVICA asciinema casts into the demo site and regenerate demos.json.

The site (index.html) renders itself entirely from demos.json, so adding or
re-recording a demo never requires editing HTML by hand -- re-run this script.

Durations, and the copy-paste command shown under each player, are both read
out of the cast files themselves -- neither can drift from what the recording
actually shows. The command is found by decoding the recording's real output
and picking the one typed line that matches that demo's COMMAND_PATTERN (see
below); it is never hand-typed, so a real filename or target name recorded on
someone else's machine appears on the page exactly as typed, not as a
generic placeholder like "scan1.uvfits".

Typical use
-----------
    # Copy freshly recorded casts out of the data directory and rebuild manifest
    python3 scripts/sync_casts.py --from ~/Intelligence/tests/vasco_0.3/casts

    # Rebuild demos.json only, using casts already in casts/
    python3 scripts/sync_casts.py

    # See what would change without writing anything
    python3 scripts/sync_casts.py --from /path/to/casts --dry-run

Adding a tenth demo
-------------------
Record it, add an entry to CATALOG below keyed by the cast's stem (e.g.
"10_imaging"), give it a COMMAND_PATTERN entry that uniquely matches the one
line in the recording you want shown (see the comment above COMMAND_PATTERN),
then re-run this script.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
CASTS_DIR = SITE_ROOT / "casts"
MANIFEST = SITE_ROOT / "demos.json"

# Idle gaps longer than this (seconds) are compressed by the player at playback
# time. Non-destructive: the cast files keep their real timings.
IDLE_LIMIT = 1.0

GROUPS = [
    ("Getting started", "No data required -- follow along on any machine."),
    ("Inspecting data", "Needs a VLBI FITS-IDI dataset."),
    ("Running the pipeline", "Needs FITS-IDI data, CASA and rPICARD."),
]

# Curated per-demo metadata. Durations, file sizes, and the displayed command
# are all measured from the cast -- nothing here is a command to display as-is.
CATALOG = {
    "01_installation": {
        "title": "Installation",
        "group": "Getting started",
        "blurb": "One script installs the whole stack -- AVICA, CASA and rPICARD -- "
                 "and reuses an existing rPICARD if it finds one.",
        "data": False,
    },
    "02_cli_tour": {
        "title": "CLI Tour",
        "group": "Getting started",
        "blurb": "Every top-level command and what its --help tells you.",
        "data": False,
    },
    "03_configuration": {
        "title": "Configuration",
        "group": "Getting started",
        "blurb": "Build an avica.inp, then use --summary to see every resolved "
                 "parameter and which layer it came from.",
        "data": False,
    },
    "04_fitsidi_check": {
        "title": "FITS-IDI Validation",
        "group": "Inspecting data",
        "blurb": "Scan a FITS-IDI file for known defects per HDU, and apply the "
                 "fixes that are available.",
        "data": True,
    },
    "05_listobs": {
        "title": "List Observations",
        "group": "Inspecting data",
        "blurb": "Print the observation metadata -- sources, antennas, scans, "
                 "frequency setup -- straight from the FITS-IDI.",
        "data": True,
    },
    "06_pipeline_run": {
        "title": "Full Pipeline Run",
        "group": "Running the pipeline",
        "blurb": "The complete nine-step reduction end to end, from raw FITS-IDI "
                 "through to the rPICARD calibration.",
        "data": True,
    },
    "07_pipeline_steps": {
        "title": "Individual Steps",
        "group": "Running the pipeline",
        "blurb": "Name the steps you want and run only those -- useful while "
                 "tuning one stage of a reduction.",
        "data": True,
    },
    "08_resume": {
        "title": "Resuming a Run",
        "group": "Running the pipeline",
        "blurb": "Pick up an interrupted reduction where it stopped with --resume, "
                 "or rewind to a chosen step with --resume-from.",
        "data": True,
    },
    "09_result": {
        "title": "Reading Results",
        "group": "Running the pipeline",
        "blurb": "The progress ladder, failure panels, full retry history and the "
                 "one-line view built for CI.",
        "data": True,
    },
}

# Regex (re.fullmatch) picking the one typed line to display as the copy-paste
# command, out of every line the recording shows after its "❯ " prompt (both
# run() and show() print that same prompt -- see demos/lib/helpers.sh). Each
# pattern is written to match exactly one demo's real invocation shape and
# reject every other command shown in that same recording. When a demo shows
# more than one candidate line, the FIRST one in playback order that matches
# wins, so pattern order only matters relative to the recording, never to this
# dict.
COMMAND_PATTERN = {
    "01_installation": r"curl -LsSf https://\S+/install\.sh \| bash",
    "02_cli_tour": r"avica --help",
    "03_configuration": r"avica pipe config --summary --inpfile \S+",
    "04_fitsidi_check": r"avica fitsidi_check --fix \S+",
    "05_listobs": r"avica listobs \S+",
    "06_pipeline_run": (
        r"avica pipe run\s{2,}--fitsfilenames\s+\S+"
        r"\s{2,}--target\s+\S+\s{2,}--configfile\s+\S+"
    ),
    "07_pipeline_steps": (
        r"avica pipe run(?: [a-zA-Z_]\w*)+\s{2,}--fitsfilenames\s+\S+"
        r"\s{2,}--target\s+\S+\s{2,}--configfile\s+\S+"
    ),
    "08_resume": (
        r"avica pipe run --resume\s{2,}--fitsfilenames\s+\S+"
        r"\s{2,}--target\s+\S+\s{2,}--configfile\s+\S+"
    ),
    "09_result": r"avica pipe result --target \S+ --configfile \S+",
}

# Strips terminal control sequences (color codes, cursor moves, the resize/
# clear codes at the top of every recording) so the decoded text is plain
# characters only.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")

# Every command the demos print is typed after this prompt (see run()/show()
# in demos/lib/helpers.sh) -- both functions use the identical glyph, so a
# "❯ "-prefixed line is "something that was actually typed on screen",
# regardless of whether that particular line was really executed or only
# illustrated. Either way its filenames and target names are real: bash
# expands $FITS/$TARGET into the string before run()/show() ever see it.
PROMPT = "❯ "  # U+276F HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT

# A .uvfits path a demo recording happened to type with its local absolute
# directory (e.g. because that machine's env.sh pointed AVICA_FITS_FILE at a
# full path) is not something a visitor can paste -- only the filename means
# anything on their machine. Collapse any such path to its basename.
UVFITS_PATH_RE = re.compile(r"(?:\S*/)+([^\s,/]+\.uvfits)")


def decode_cast_text(path: Path) -> str:
    """Concatenate every terminal-output ("o") event's payload, in order."""
    chunks: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        fh.readline()  # header
        for line in fh:
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if len(event) >= 2 and event[1] == "o":
                chunks.append(str(event[2]))
    return "".join(chunks)


def typed_commands(cast_text: str) -> list[str]:
    """Every line the recording shows right after its "❯ " prompt, in order."""
    clean = ANSI_RE.sub("", cast_text).replace("\r\n", "\n").replace("\r", "")
    return [
        line[len(PROMPT):]
        for line in clean.split("\n")
        if line.startswith(PROMPT)
    ]


def extract_command(cast: Path, stem: str) -> str:
    """The one real command to show under this demo's player.

    Decodes what the recording actually printed and returns the first typed
    line matching this demo's COMMAND_PATTERN -- i.e. the literal text a
    viewer would see if they watched the recording themselves, filenames and
    target names included. Raises if no line matches, since a silently stale
    or blank command is worse than a loud failure at build time.
    """
    pattern = COMMAND_PATTERN.get(stem)
    if pattern is None:
        raise KeyError(f"no COMMAND_PATTERN entry for {stem!r}")
    for line in typed_commands(decode_cast_text(cast)):
        if re.fullmatch(pattern, line):
            return UVFITS_PATH_RE.sub(r"\1", line)
    raise ValueError(
        f"{cast.name}: no typed line matched COMMAND_PATTERN[{stem!r}] "
        f"({pattern!r}) -- the recording changed shape, or the pattern needs updating"
    )


def parse_cast(path: Path) -> dict:
    """Return header, raw duration and idle-capped duration for a v2 cast."""
    stamps: list[float] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        header = json.loads(fh.readline())
        for line in fh:
            line = line.strip()
            if line.startswith("["):
                try:
                    stamps.append(json.loads(line)[0])
                except (ValueError, IndexError):
                    pass
    raw = stamps[-1] if stamps else 0.0
    capped, prev = 0.0, 0.0
    for t in stamps:
        capped += min(t - prev, IDLE_LIMIT)
        prev = t
    return {"header": header, "raw": raw, "capped": capped}


def clock(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--from", dest="source", metavar="DIR", type=Path,
        help="Directory holding freshly recorded .cast files (e.g. your data "
             "directory's casts/ folder). Omit to rebuild from casts/ in place.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change; write nothing.",
    )
    args = ap.parse_args(argv)

    if args.source:
        source = args.source.expanduser().resolve()
        if not source.is_dir():
            print(f"error: --from {source} is not a directory", file=sys.stderr)
            return 1
        found = sorted(source.glob("*.cast"))
        if not found:
            print(f"error: no .cast files in {source}", file=sys.stderr)
            return 1
        CASTS_DIR.mkdir(exist_ok=True)
        for cast in found:
            target = CASTS_DIR / cast.name
            print(f"{'would copy' if args.dry_run else 'copied'}  {cast.name}")
            if not args.dry_run:
                shutil.copyfile(cast, target)
                target.chmod(0o644)

    casts = sorted(CASTS_DIR.glob("*.cast"))
    if not casts:
        print(f"error: no casts in {CASTS_DIR}", file=sys.stderr)
        return 1

    demos, unknown = [], []
    for cast in casts:
        stem = cast.stem
        meta = CATALOG.get(stem)
        if meta is None:
            unknown.append(stem)
            continue
        info = parse_cast(cast)
        demos.append({
            "id": stem,
            "n": stem.split("_")[0],
            "title": meta["title"],
            "group": meta["group"],
            "blurb": meta["blurb"],
            "command": extract_command(cast, stem),
            "data": meta["data"],
            "cast": f"casts/{cast.name}",
            "cols": info["header"].get("width", 200),
            "rows": info["header"].get("height", 50),
            "rawSeconds": round(info["raw"], 1),
            "rawClock": clock(info["raw"]),
            "playClock": clock(info["capped"]),
            # Frame shown before playback: late enough that the terminal has
            # filled, so the page never sits on a mostly-blank screen.
            "posterAt": clock(info["capped"] * 0.65),
            "trimmed": info["raw"] - info["capped"] > 5,
            "bytes": cast.stat().st_size,
        })

    manifest = {
        "idleTimeLimit": IDLE_LIMIT,
        "groups": [{"name": n, "note": d} for n, d in GROUPS],
        "demos": demos,
    }

    if args.dry_run:
        print(json.dumps(manifest, indent=2))
    else:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"{'demo':<22}{'play':>7}{'actual':>9}  trimmed")
    print("-" * 48)
    for d in demos:
        mark = "yes" if d["trimmed"] else "-"
        print(f"{d['id']:<22}{d['playClock']:>7}{d['rawClock']:>9}  {mark}")
    print("-" * 48)
    print(f"{len(demos)} demos -> {MANIFEST.name}"
          f"{' (dry run, not written)' if args.dry_run else ''}")
    if unknown:
        print(f"\nwarning: no CATALOG entry, skipped: {', '.join(unknown)}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
