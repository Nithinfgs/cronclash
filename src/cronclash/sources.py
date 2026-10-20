"""Find cron schedules in crontabs, GitHub Actions workflows and Kubernetes CronJobs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox"}
MAX_BYTES = 1_000_000

_GH_CRON = re.compile(r"""^\s*-?\s*cron:\s*(['"]?)(?P<e>.+?)\1\s*(?:#.*)?$""")
_K8S_SCHEDULE = re.compile(r"""^\s*schedule:\s*(['"]?)(?P<e>.+?)\1\s*(?:#.*)?$""")
_K8S_NAME = re.compile(r"""^\s{2}name:\s*(?P<n>\S+)""")
_ENV_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")


@dataclass(frozen=True)
class Job:
    name: str
    expr: str
    source: str
    line: int


def _is_crontab_name(base: str) -> bool:
    return base in ("crontab", "cron") or base.endswith((".cron", ".crontab"))


def _yaml_jobs(path: str, lines: List[str]) -> List[Job]:
    text = "\n".join(lines)
    stem = os.path.basename(path)
    jobs: List[Job] = []
    if re.search(r"^kind:\s*CronJob\b", text, re.M):
        name = stem
        for ln in lines:
            m = _K8S_NAME.match(ln)
            if m:
                name = m.group("n")
                break
        for i, ln in enumerate(lines, 1):
            m = _K8S_SCHEDULE.match(ln)
            if m:
                jobs.append(Job(f"cronjob/{name}", m.group("e"), path, i))
        return jobs
    n = 0
    for i, ln in enumerate(lines, 1):
        m = _GH_CRON.match(ln)
        if m:
            n += 1
            jobs.append(Job(f"{stem}#{n}", m.group("e"), path, i))
    return jobs


def _crontab_jobs(path: str, lines: List[str]) -> List[Job]:
    jobs: List[Job] = []
    for i, raw in enumerate(lines, 1):
        ln = raw.strip()
        if not ln or ln.startswith("#") or _ENV_LINE.match(ln):
            continue
        toks = ln.split()
        if toks[0].startswith("@"):
            expr, rest = toks[0], toks[1:]
        else:
            expr, rest = " ".join(toks[:5]), toks[5:]
        label = os.path.basename(rest[0]) if rest else "?"
        # /etc/cron.d lines carry a user column before the command
        if len(rest) > 1 and rest[0] in ("root", "www-data", "nobody"):
            label = os.path.basename(rest[1])
        jobs.append(Job(f"{label}@L{i}", expr, path, i))
    return jobs


def read_file(path: str) -> List[Job]:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return []
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    base = os.path.basename(path)
    if base.endswith((".yml", ".yaml")):
        return _yaml_jobs(path, lines)
    if _is_crontab_name(base) or os.path.basename(os.path.dirname(path)) == "cron.d":
        return _crontab_jobs(path, lines)
    return []


def discover(paths: Iterable[str]) -> List[Job]:
    jobs: List[Job] = []
    for p in paths:
        if os.path.isfile(p):
            base = os.path.basename(p)
            # an explicitly named file is trusted to be a crontab unless it is YAML
            if base.endswith((".yml", ".yaml")):
                jobs.extend(read_file(p))
            else:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    jobs.extend(_crontab_jobs(p, fh.read().splitlines()))
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for f in sorted(files):
                jobs.extend(read_file(os.path.join(root, f)))
    return jobs


def inline(exprs: Iterable[str]) -> List[Job]:
    return [Job(f"cli#{i}", e, "<cli>", 0) for i, e in enumerate(exprs, 1)]


def split_valid(jobs: Iterable[Job]) -> Tuple[List[Job], List[Tuple[Job, str]]]:
    from .cron import CronError, parse
    ok: List[Job] = []
    bad: List[Tuple[Job, str]] = []
    for j in jobs:
        try:
            parse(j.expr)
            ok.append(j)
        except CronError as e:
            bad.append((j, str(e)))
    return ok, bad
