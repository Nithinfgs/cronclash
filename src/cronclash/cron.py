"""A small, strict parser for 5-field cron expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet

MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}
DOWS = {d: i for i, d in enumerate("sun mon tue wed thu fri sat".split())}

MACROS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}


class CronError(ValueError):
    """Raised when an expression cannot be parsed."""


@dataclass(frozen=True)
class Field:
    values: FrozenSet[int]
    star: bool  # unrestricted (starts with '*' or '?')
    raw: str


@dataclass(frozen=True)
class Cron:
    expr: str
    minute: Field
    hour: Field
    dom: Field
    month: Field
    dow: Field

    def matches_day(self, month: int, dom: int, dow: int) -> bool:
        """dow: 0=Sunday. Vixie semantics: if both day fields are restricted, either may match."""
        if month not in self.month.values:
            return False
        dom_ok = dom in self.dom.values
        dow_ok = dow in self.dow.values
        if self.dom.star or self.dow.star:
            return dom_ok and dow_ok
        return dom_ok or dow_ok


def _number(tok: str, names: Dict[str, int], lo: int, hi: int, label: str) -> int:
    t = tok.lower()
    if t in names:
        return names[t]
    if not t.isdigit():
        raise CronError(f"bad {label} value {tok!r}")
    n = int(t)
    if label == "day-of-week" and n == 7:
        return 0
    if not lo <= n <= hi:
        raise CronError(f"{label} value {n} out of range {lo}-{hi}")
    return n


def _parse_field(text: str, lo: int, hi: int, label: str,
                 names: Dict[str, int] | None = None) -> Field:
    names = names or {}
    out: set[int] = set()
    for part in text.split(","):
        if not part:
            raise CronError(f"empty item in {label} field {text!r}")
        base, _, step_s = part.partition("/")
        step = 1
        if _:
            if not step_s.isdigit() or int(step_s) < 1:
                raise CronError(f"bad step {step_s!r} in {label} field")
            step = int(step_s)
        if base in ("*", "?"):
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start = _number(a, names, lo, hi, label)
            end = _number(b, names, lo, hi, label)
            if label == "day-of-week" and b == "7":
                end = 7
            if start > end:
                raise CronError(f"descending range {base!r} in {label} field")
        else:
            start = _number(base, names, lo, hi, label)
            end = hi if step_s else start
        for v in range(start, end + 1, step):
            out.add(0 if (label == "day-of-week" and v == 7) else v)
    return Field(frozenset(out), text[:1] in "*?", text)


def parse(expr: str) -> Cron:
    expr = expr.strip()
    expr = MACROS.get(expr.lower(), expr)
    parts = expr.split()
    if len(parts) != 5:
        raise CronError(f"expected 5 fields, got {len(parts)}: {expr!r}")
    m, h, dom, mon, dow = parts
    return Cron(
        expr=expr,
        minute=_parse_field(m, 0, 59, "minute"),
        hour=_parse_field(h, 0, 23, "hour"),
        dom=_parse_field(dom, 1, 31, "day-of-month"),
        month=_parse_field(mon, 1, 12, "month", MONTHS),
        dow=_parse_field(dow, 0, 7, "day-of-week", DOWS),
    )
