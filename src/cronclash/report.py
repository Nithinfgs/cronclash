"""Plain-text and JSON rendering."""

from __future__ import annotations

import dataclasses
import json
from typing import List, Tuple

from .analyze import DAY_NAMES, Report
from .sources import Job

_SHADES = " .:-=+*#%@"


def heat_text(heat: List[List[int]]) -> str:
    top = max((v for row in heat for v in row), default=0) or 1
    lines = ["      " + "".join(str(h // 10) if h % 6 == 0 else " " for h in range(24)) + "   hours 00-23, darker = busier"]
    for wd, row in enumerate(heat):
        cells = "".join(_SHADES[min(len(_SHADES) - 1, round(v / top * (len(_SHADES) - 1)))] for v in row)
        lines.append(f"  {DAY_NAMES[wd]} {cells}")
    return "\n".join(lines)


def text(rep: Report, jobs: List[Job], bad: List[Tuple[Job, str]], limit: int = 10) -> str:
    out = [f"cronclash: {len(jobs)} schedule(s), {rep.total_firings} firings in {rep.days} days from {rep.start}",
           f"peak concurrency: {rep.peak}   firings exactly on the hour: {rep.top_of_hour_pct}%", ""]
    for j, why in bad:
        out.append(f"skipped {j.source}:{j.line} ({j.expr}): {why}")
    if bad:
        out.append("")
    out += ["load by weekday and hour:", heat_text(rep.heatmap), ""]
    if rep.collisions:
        out.append(f"worst collisions (shown {min(limit, len(rep.collisions))} of {len(rep.collisions)}):")
        for c in rep.collisions[:limit]:
            out.append(f"  {c.days} {c.hhmm}  {len(c.jobs)} jobs  x{c.occurrences}  {', '.join(c.jobs)}")
    else:
        out.append("no collisions at or above the threshold.")
    if rep.suggestions:
        out += ["", "suggested staggering (minute offsets only, cadence unchanged):"]
        for s in rep.suggestions:
            out.append(f"  {s.job}: '{s.old}' -> '{s.new}'  (+{s.shift}m)")
    return "\n".join(out)


def as_json(rep: Report, jobs: List[Job], bad: List[Tuple[Job, str]]) -> str:
    return json.dumps({
        "report": dataclasses.asdict(rep),
        "jobs": [dataclasses.asdict(j) for j in jobs],
        "skipped": [{"job": dataclasses.asdict(j), "error": e} for j, e in bad],
    }, indent=2)
