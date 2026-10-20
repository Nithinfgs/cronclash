from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import List, Optional

from . import __version__, report, sources
from .analyze import analyze


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cronclash",
        description="Find cron jobs that fire at the same moment. Reads crontabs, GitHub Actions "
                    "workflows and Kubernetes CronJobs.")
    p.add_argument("paths", nargs="*", help="files or directories to scan (default: current directory)")
    p.add_argument("--cron", action="append", default=[], metavar="EXPR",
                   help="add a schedule by hand, e.g. --cron '0 * * * *' (repeatable)")
    p.add_argument("--days", type=int, default=28, help="simulation window in days (default 28)")
    p.add_argument("--start", type=dt.date.fromisoformat, default=None, metavar="YYYY-MM-DD",
                   help="first day of the window (default: today)")
    p.add_argument("--threshold", type=int, default=3,
                   help="report minutes where at least this many jobs fire (default 3)")
    p.add_argument("--max-concurrent", type=int, default=None, metavar="N",
                   help="exit 1 if more than N jobs ever fire in the same minute (for CI)")
    p.add_argument("--no-suggest", action="store_true", help="skip stagger suggestions")
    p.add_argument("--limit", type=int, default=10, help="collisions to print (default 10)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--version", action="version", version=f"cronclash {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.days < 1 or args.days > 400:
        print("cronclash: --days must be between 1 and 400", file=sys.stderr)
        return 2
    paths = args.paths or ([] if args.cron else ["."])
    jobs = sources.discover(paths) + sources.inline(args.cron)
    ok, bad = sources.split_valid(jobs)
    if not ok:
        print("cronclash: no valid cron schedules found" + (f" ({len(bad)} invalid)" if bad else ""),
              file=sys.stderr)
        return 2
    # job names must be unique for the simulation
    seen = {}
    uniq = []
    for j in ok:
        n = seen.get(j.name, 0)
        seen[j.name] = n + 1
        uniq.append(j if n == 0 else sources.Job(f"{j.name}~{n + 1}", j.expr, j.source, j.line))
    rep = analyze(uniq, args.start or dt.date.today(), args.days, args.threshold, not args.no_suggest)
    print(report.as_json(rep, uniq, bad) if args.json else report.text(rep, uniq, bad, args.limit))
    if args.max_concurrent is not None and rep.peak > args.max_concurrent:
        return 1
    return 0
