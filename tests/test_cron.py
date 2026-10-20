import datetime as dt
import unittest

from cronclash.cron import CronError, parse
from cronclash.analyze import firings


class ParseTests(unittest.TestCase):
    def test_fields(self):
        c = parse("*/15 0-2 1,15 jan,mar mon-fri")
        self.assertEqual(sorted(c.minute.values), [0, 15, 30, 45])
        self.assertEqual(sorted(c.hour.values), [0, 1, 2])
        self.assertEqual(sorted(c.month.values), [1, 3])
        self.assertEqual(sorted(c.dow.values), [1, 2, 3, 4, 5])

    def test_sunday_as_7_and_macros(self):
        self.assertEqual(sorted(parse("0 0 * * 7").dow.values), [0])
        self.assertEqual(parse("@hourly").expr, "0 * * * *")

    def test_step_from_start(self):
        self.assertEqual(sorted(parse("5/20 * * * *").minute.values), [5, 25, 45])

    def test_errors(self):
        for bad in ["* * * *", "60 * * * *", "* 24 * * *", "5-1 * * * *", "*/0 * * * *", "a * * * *"]:
            with self.assertRaises(CronError, msg=bad):
                parse(bad)


class FiringTests(unittest.TestCase):
    start = dt.date(2026, 10, 19)  # a Monday

    def test_daily_count(self):
        self.assertEqual(len(firings(parse("30 4 * * *"), self.start, 10)), 10)

    def test_weekday_only(self):
        # Mon..Sun window: Mon-Fri only
        self.assertEqual(len(firings(parse("0 0 * * 1-5"), self.start, 7)), 5)

    def test_dom_or_dow_semantics(self):
        # 1st of month OR Monday: Oct 19-Nov 1 contains Mondays 19, 26 and Nov 1
        days = {m // 1440 for m in firings(parse("0 0 1 * 1"), self.start, 14)}
        self.assertEqual(days, {0, 7, 13})

    def test_every_minute(self):
        self.assertEqual(len(firings(parse("* * * * *"), self.start, 1)), 1440)
