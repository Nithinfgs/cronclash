# cronclash

Find cron jobs that fire at the same moment, and spread them out.

Every team ends up with a dozen things scheduled at `0 2 * * *`: the backup, the log rotation, the nightly CI build,
the Kubernetes export. They all wake at 02:00:00, fight for the same database and runner pool, and the failure looks
random. `cronclash` reads all your schedules in one pass, simulates the real calendar, and tells you where they pile up.

It reads:

- **crontab files** (`crontab`, `*.cron`, `*.crontab`, `/etc/cron.d/*`), including `@daily`-style macros
- **GitHub Actions** workflows (`schedule: - cron:`)
- **Kubernetes** `CronJob` manifests (`spec.schedule`)
- anything you pass by hand with `--cron`

No dependencies, no network, Python 3.9+.

## Install

```bash
pip install git+https://github.com/Nithinfgs/cronclash
```

Or run from a checkout without installing: `PYTHONPATH=src python3 -m cronclash`.

## Usage

```bash
cronclash                       # scan the current directory
cronclash infra/ ops/crontab    # scan specific paths
cronclash --cron '0 * * * *' --cron '@hourly' --days 7
cronclash --max-concurrent 2    # exit 1 if 3+ jobs ever share a minute (CI gate)
cronclash --json                # machine-readable
```

Example (`cronclash examples --start 2026-10-19`):

```text
cronclash: 6 schedule(s), 812 firings in 28 days from 2026-10-19
peak concurrency: 5   firings exactly on the hour: 100.0%

load by weekday and hour:
      0     0     1     1        hours 00-23, darker = busier
  Sun =:@:::::::::::::::::::::
  Mon =:@:::::::::::::::::::::
  Tue =:@:::::::::::::::::::::
  Wed =:@:::::::::::::::::::::
  Thu =:@:::::::::::::::::::::
  Fri =:@:::::::::::::::::::::
  Sat =:@:::::::::::::::::::::

worst collisions (shown 1 of 1):
  daily 02:00  5 jobs  x28  backup-db.sh@L2, cronjob/export-metrics, nightly.yml#1, rotate-logs.sh@L3, sync-cache.sh@L4

suggested staggering (minute offsets only, cadence unchanged):
  sync-cache.sh@L4: '0 * * * *' -> '1 * * * *'  (+1m)
  cronjob/export-metrics: '0 2 * * *' -> '2 2 * * *'  (+2m)
  backup-db.sh@L2: '0 2 * * *' -> '3 2 * * *'  (+3m)
  rotate-logs.sh@L3: '0 2 * * *' -> '4 2 * * *'  (+4m)
```

### What it tells you

- **Peak concurrency** and the share of firings that land exactly on the hour.
- A **weekday x hour load map**.
- **Collisions**: minutes where at least `--threshold` jobs fire together, grouped by time of day and weekday so a
  daily pile-up shows as one line, not 28.
- **Stagger suggestions**: a greedy search that shifts the *minute* of jobs to the offset that lowers the peak most.

### Options

| Option | Default | Meaning |
|---|---|---|
| `--days N` | 28 | simulation window (1-400) |
| `--start YYYY-MM-DD` | today | first day of the window |
| `--threshold N` | 3 | minimum simultaneous jobs to report |
| `--max-concurrent N` | off | exit status 1 if the peak exceeds N |
| `--limit N` | 10 | collisions to print |
| `--no-suggest` | off | skip suggestions |
| `--json` | off | JSON output |

Exit codes: `0` ok, `1` gate exceeded, `2` bad input or nothing found.

## How it works

Each expression is parsed strictly (lists, ranges, steps, month and weekday names, `7` as Sunday). Firings are
expanded over a concrete calendar window, so "1st of the month or Monday" (the standard day-of-month / day-of-week
OR rule) and month lengths behave as they do in a real cron.

Suggestions only rewrite jobs whose minute field is an explicit list (`0`, `0,30`). They never touch `*/5` or
ranges, and a shift never crosses the hour boundary, so the cadence and the hour of each run stay the same.

## Limitations

- **Time zones are ignored.** A crontab runs in the server's zone, GitHub Actions in UTC, and a CronJob in the
  controller's zone or its `timeZone` field. Convert to one zone first if they differ, or you will see false
  collisions and miss real ones.
- YAML is read line by line, not fully parsed. Schedules built from templates (Helm values, anchors) are not seen;
  pass them with `--cron`.
- Job *duration* is unknown, so a 02:00 job that runs for an hour overlaps a 02:30 job without being reported.
  Only start-time collisions are detected.

## Development

```bash
python -m unittest discover -s tests
```

## License

MIT
