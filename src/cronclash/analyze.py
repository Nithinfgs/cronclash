"""Simulate firings over a window, find collisions, and suggest minute offsets."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set, Tuple

from .cron import Cron, parse
from .sources import Job

DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


@dataclass
class Collision:
    days: str  # "daily", "Mon,Wed" ...
    hhmm: str
    jobs: List[str]
    occurrences: int


@dataclass
class Suggestion:
    job: str
    old: str
    new: str
    shift: int


@dataclass
class Report:
    start: str
    days: int
    total_firings: int
    peak: int
    top_of_hour_pct: float
    collisions: List[Collision]
    suggestions: List[Suggestion]
    heatmap: List[List[int]] = field(default_factory=list)  # [weekday][hour]


def firings(cron: Cron, start: dt.date, days: int) -> List[int]:
    """Minute indexes (from start 00:00) at which the cron fires."""
    out: List[int] = []
    mins = sorted(cron.minute.values)
    hrs = sorted(cron.hour.values)
    for d in range(days):
        day = start + dt.timedelta(days=d)
        if not cron.matches_day(day.month, day.day, (day.weekday() + 1) % 7):
            continue
        base = d * 1440
        out.extend(base + h * 60 + m for h in hrs for m in mins)
    return out


def _load(slots: Dict[int, List[int]]) -> int:
    return max((len(v) for v in slots.values()), default=0)


def _shiftable(cron: Cron) -> bool:
    """Only explicit minute lists can be shifted without changing the cadence."""
    f = cron.minute.raw
    return "*" not in f and "/" not in f and "-" not in f and "?" not in f


def _shift_expr(cron: Cron, delta: int) -> str:
    mins = ",".join(str(m + delta) for m in sorted(cron.minute.values))
    return " ".join([mins] + cron.expr.split()[1:])


def suggest(parsed: Sequence[Tuple[Job, Cron]], fires: Dict[str, List[int]]) -> List[Suggestion]:
    """Greedy: move shiftable jobs to the minute offset that minimizes the peak load."""
    load: Dict[int, int] = defaultdict(int)
    for v in fires.values():
        for s in v:
            load[s] += 1
    out: List[Suggestion] = []
    movable = [(j, c) for j, c in parsed if _shiftable(c) and fires[j.name]]
    movable.sort(key=lambda jc: -len(fires[jc[0].name]))
    for job, cron in movable:
        slots = fires[job.name]
        top = max(cron.minute.values)
        best = (0, None)  # (score, delta)
        for delta in range(0, 60 - top):
            peak = 0
            sq = 0
            for s in slots:
                l = load[s + delta] - (1 if delta == 0 else 0) + 1
                peak = max(peak, l)
                sq += l * l
            score = (peak, sq, delta)
            if best[1] is None or score < best[0]:
                best = (score, delta)
        delta = best[1]
        if delta:
            for s in slots:
                load[s] -= 1
                load[s + delta] += 1
            fires[job.name] = [s + delta for s in slots]
            out.append(Suggestion(job.name, cron.expr, _shift_expr(cron, delta), delta))
    return out


def analyze(jobs: Sequence[Job], start: dt.date, days: int = 28,
            threshold: int = 3, want_suggestions: bool = True) -> Report:
    parsed = [(j, parse(j.expr)) for j in jobs]
    fires = {j.name: firings(c, start, days) for j, c in parsed}
    slots: Dict[int, List[str]] = defaultdict(list)
    for name, v in fires.items():
        for s in v:
            slots[s].append(name)

    total = sum(len(v) for v in fires.values())
    top_hour = sum(1 for s, names in slots.items() if s % 60 == 0 for _ in names)
    heat = [[0] * 24 for _ in range(7)]
    for s, names in slots.items():
        d = start + dt.timedelta(days=s // 1440)
        heat[(d.weekday() + 1) % 7][(s % 1440) // 60] += len(names)

    grouped: Dict[Tuple[int, Tuple[str, ...]], Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for s, names in slots.items():
        if len(names) >= threshold:
            d = start + dt.timedelta(days=s // 1440)
            grouped[(s % 1440, tuple(sorted(names)))][(d.weekday() + 1) % 7] += 1
    collisions = []
    for (mn, names), per_day in grouped.items():
        label = "daily" if len(per_day) == 7 else ",".join(DAY_NAMES[w] for w in sorted(per_day))
        collisions.append(Collision(label, f"{mn // 60:02d}:{mn % 60:02d}", list(names),
                                    sum(per_day.values())))
    collisions.sort(key=lambda c: (-len(c.jobs), -c.occurrences, c.hhmm, c.days))

    before_peak = _load(slots)
    suggestions = suggest(parsed, fires) if want_suggestions and before_peak > 1 else []
    return Report(
        start=start.isoformat(), days=days, total_firings=total, peak=before_peak,
        top_of_hour_pct=round(100 * top_hour / total, 1) if total else 0.0,
        collisions=collisions, suggestions=suggestions, heatmap=heat,
    )
