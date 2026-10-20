import datetime as dt
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from cronclash import sources
from cronclash.analyze import analyze
from cronclash.cli import main

START = dt.date(2026, 10, 19)


def jobs(*exprs):
    return sources.inline(exprs)


class AnalyzeTests(unittest.TestCase):
    def test_collision_detected_and_grouped(self):
        rep = analyze(jobs("0 * * * *", "0 * * * *", "0 * * * *"), START, 7, threshold=3)
        self.assertEqual(rep.peak, 3)
        self.assertEqual(rep.top_of_hour_pct, 100.0)
        self.assertEqual(len(rep.collisions), 24)  # one per hour, grouped across days
        self.assertTrue(all(c.days == "daily" for c in rep.collisions))

    def test_suggestions_remove_collisions_without_changing_cadence(self):
        rep = analyze(jobs("0 * * * *", "0 * * * *", "0 * * * *"), START, 7)
        self.assertEqual(len(rep.suggestions), 2)
        new = jobs(*["0 * * * *"] + [s.new for s in rep.suggestions])
        after = analyze(new, START, 7, want_suggestions=False)
        self.assertEqual(after.peak, 1)
        self.assertEqual(after.total_firings, rep.total_firings)

    def test_step_expressions_are_never_rewritten(self):
        rep = analyze(jobs("*/5 * * * *", "*/5 * * * *"), START, 1)
        self.assertEqual(rep.suggestions, [])

    def test_no_wrap_past_the_hour(self):
        rep = analyze(jobs("58 * * * *", "58 * * * *"), START, 1)
        for s in rep.suggestions:
            self.assertLessEqual(s.shift, 1)

    def test_no_collisions(self):
        rep = analyze(jobs("1 * * * *", "2 * * * *"), START, 3)
        self.assertEqual(rep.collisions, [])
        self.assertEqual(rep.peak, 1)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def test_all_three_sources(self):
        self.write(".github/workflows/nightly.yml",
                   "on:\n  schedule:\n    - cron: '0 2 * * *'\n    - cron: \"30 2 * * 1\" # weekly\n")
        self.write("k8s/job.yaml",
                   "apiVersion: batch/v1\nkind: CronJob\nmetadata:\n  name: report\nspec:\n  schedule: \"0 2 * * *\"\n")
        self.write("ops/crontab", "MAILTO=me\n# comment\n0 2 * * * /usr/bin/backup.sh\n@daily /opt/clean\n")
        self.write("node_modules/x/crontab", "0 0 * * * ignored\n")
        found = sources.discover([self.root])
        self.assertEqual(sorted(j.expr for j in found),
                         ["0 2 * * *", "0 2 * * *", "0 2 * * *", "30 2 * * 1", "@daily"])
        self.assertIn("cronjob/report", {j.name for j in found})

    def test_cli_json_and_gate(self):
        self.write("crontab", "0 * * * * a\n0 * * * * b\n0 * * * * c\nnot a cron line here ok\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([self.root, "--json", "--days", "2", "--start", "2026-10-19", "--max-concurrent", "2"])
        self.assertEqual(code, 1)
        data = json.loads(out.getvalue())
        self.assertEqual(data["report"]["peak"], 3)
        self.assertEqual(len(data["skipped"]), 1)

    def test_cli_passes_gate_and_errors(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--cron", "5 * * * *", "--days", "1", "--max-concurrent", "1"]), 0)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--cron", "nope"]), 2)
            self.assertEqual(main(["--cron", "* * * * *", "--days", "0"]), 2)

    def test_duplicate_names_do_not_merge(self):
        self.write("a/crontab", "0 * * * * run\n")
        self.write("b/crontab", "0 * * * * run\n")
        out = io.StringIO()
        with redirect_stdout(out):
            main([self.root, "--json", "--days", "1", "--start", "2026-10-19"])
        self.assertEqual(json.loads(out.getvalue())["report"]["peak"], 2)


if __name__ == "__main__":
    unittest.main()
