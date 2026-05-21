"""CLI for RMTA.

Usage:
    python -m rmta triage [path_to_milestone.json] [--as-of YYYY-MM-DD]
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path

from .adapters import JiraAdapter
from .projection import project
from .triage import triage, summarise_top3
from .report import render


PKG_DIR = Path(__file__).parent
DEFAULT_MILESTONE = PKG_DIR.parent / "samples" / "jira_milestone.json"


def main():
    p = argparse.ArgumentParser(prog="rmta")
    sub = p.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("triage", help="Run the daily triage scan")
    pt.add_argument("milestone", nargs="?", default=str(DEFAULT_MILESTONE),
                    help="path to milestone JSON (Jira-shaped)")
    pt.add_argument("--as-of", default=None,
                    help="treat as_of date as YYYY-MM-DD (default: now)")
    pt.add_argument("--out", default=None,
                    help="write report to this path (default: stdout)")
    args = p.parse_args()

    if args.cmd != "triage":
        p.error(f"Unknown command {args.cmd}")

    if args.as_of:
        as_of = datetime.fromisoformat(args.as_of).replace(tzinfo=timezone.utc)
    else:
        as_of = datetime.now(timezone.utc)

    adapter = JiraAdapter(args.milestone)
    milestone = adapter.fetch_milestone("")     # mock takes any id

    projection = project(milestone, as_of)
    flags = triage(milestone, projection, as_of)
    top3 = summarise_top3(flags, milestone, projection)

    report = render(milestone, projection, flags, top3, as_of)

    if args.out:
        Path(args.out).write_text(report)
        print(f"Wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
