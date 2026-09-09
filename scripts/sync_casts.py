#!/usr/bin/env python3
"""Sync AVICA asciinema casts into the demo site and regenerate demos.json.

The site (index.html) renders itself entirely from demos.json, so adding or
re-recording a demo never requires editing HTML by hand -- re-run this script.

Durations are computed from the cast files themselves, so the numbers shown on
the page can never drift from the actual recordings.

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
Record it, then add an entry to CATALOG below keyed by the cast's stem
(e.g. "10_imaging"), and re-run this script.
"""

from __future__ import annotations

import argparse
import json
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

# Curated per-demo metadata. Durations and file sizes are measured, not stored.
CATALOG = {
    "01_installation": {
        "title": "Installation",
        "group": "Getting started",
        "blurb": "One script installs the whole stack -- AVICA, CASA and rPICARD -- "
                 "and reuses an existing rPICARD if it finds one.",
        "command": "curl -fsSL https://raw.githubusercontent.com/avikhagol/avica/main/install.sh -o install.sh\nbash install.sh",
        "data": False,
    },
    "02_cli_tour": {
        "title": "CLI Tour",
        "group": "Getting started",
        "blurb": "Every top-level command and what its --help tells you.",
        "command": "avica --help",
        "data": False,
    },
    "03_configuration": {
        "title": "Configuration",
        "group": "Getting started",
        "blurb": "Build an avica.inp, then use --summary to see every resolved "
                 "parameter and which layer it came from.",
        "command": "avica pipe config --summary --inpfile avica.inp",
        "data": False,
    },
    "04_fitsidi_check": {
        "title": "FITS-IDI Validation",
        "group": "Inspecting data",
        "blurb": "Scan a FITS-IDI file for known defects per HDU, and apply the "
                 "fixes that are available.",
        "command": "avica fitsidi_check scan1.uvfits --fix --desc",
        "data": True,
    },
    "05_listobs": {
        "title": "List Observations",
        "group": "Inspecting data",
        "blurb": "Print the observation metadata -- sources, antennas, scans, "
                 "frequency setup -- straight from the FITS-IDI.",
        "command": "avica listobs scan1.uvfits",
        "data": True,
    },
    "06_pipeline_run": {
        "title": "Full Pipeline Run",
        "group": "Running the pipeline",
        "blurb": "The complete nine-step reduction end to end, from raw FITS-IDI "
                 "through to the rPICARD calibration.",
        "command": "avica pipe run --fitsfilenames scan1.uvfits,scan2.uvfits --target J1234+5678",
        "data": True,
    },
    "07_pipeline_steps": {
        "title": "Individual Steps",
        "group": "Running the pipeline",
        "blurb": "Name the steps you want and run only those -- useful while "
                 "tuning one stage of a reduction.",
        "command": "avica pipe run preprocess_fitsidi fits_to_ms --fitsfilenames scan1.uvfits",
        "data": True,
    },
    "08_resume": {
        "title": "Resuming a Run",
        "group": "Running the pipeline",
        "blurb": "Pick up an interrupted reduction where it stopped with --resume, "
                 "or rewind to a chosen step with --resume-from.",
        "command": "avica pipe run --resume --target J1234+5678",
        "data": True,
    },
    "09_result": {
        "title": "Reading Results",
        "group": "Running the pipeline",
        "blurb": "The progress ladder, failure panels, full retry history and the "
                 "one-line view built for CI.",
        "command": "avica pipe result --target J1234+5678",
        "data": True,
    },
}


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
            "command": meta["command"],
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
