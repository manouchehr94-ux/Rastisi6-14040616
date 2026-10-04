import datetime as dt
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.core import jalali_utils as ju

TEHRAN = ZoneInfo("Asia/Tehran")


class JalaliConversionTests(SimpleTestCase):
    def test_known_conversions(self):
        self.assertEqual(ju.jalali_to_gregorian(1405, 7, 1), dt.date(2026, 9, 23))
        self.assertEqual(ju.jalali_to_gregorian(1405, 8, 30), dt.date(2026, 11, 21))
        self.assertEqual(ju.gregorian_to_jalali(dt.date(2026, 9, 23)), (1405, 7, 1))

    def test_days_in_month_and_leap(self):
        self.assertEqual(ju.jalali_days_in_month(1405, 7), 30)
        self.assertEqual(ju.jalali_days_in_month(1405, 1), 31)
        self.assertEqual(ju.jalali_days_in_month(1403, 12), 30)  # leap
        self.assertEqual(ju.jalali_days_in_month(1404, 12), 29)  # non-leap
        self.assertTrue(ju.is_jalali_leap(1403))
        self.assertFalse(ju.is_jalali_leap(1404))

    def test_invalid_dates_rejected(self):
        for args in [(1404, 12, 30), (1405, 13, 1), (1405, 7, 31), (1405, 0, 5)]:
            with self.assertRaises(ju.JalaliDateError):
                ju.jalali_to_gregorian(*args)

    def test_parse_accepts_persian_digits_and_separators(self):
        expected = dt.date(1991, 8, 14)
        for raw in ["1370/05/23", "۱۳۷۰/۰۵/۲۳", "1370-5-23", "۱۳۷۰.۵.۲۳"]:
            self.assertEqual(ju.parse_jalali_date(raw), expected, raw)

    def test_parse_rejects_garbage(self):
        for raw in ["", "abc", "1370/13/01", "1370/02", "1370/02/32", "1404/12/30", "0001/01/01"]:
            with self.assertRaises(ju.JalaliDateError, msg=raw):
                ju.parse_jalali_date(raw)

    def test_format(self):
        self.assertEqual(ju.format_jalali(dt.date(2026, 9, 23)), "1405/07/01")
        self.assertEqual(ju.format_jalali(None), "")


class MonthRangeTests(SimpleTestCase):
    def test_mehr_to_aban_1405_covers_both_months_entirely(self):
        start, end = ju.jalali_month_range_bounds(1405, 7, 8, TEHRAN)
        self.assertEqual(start, dt.datetime(2026, 9, 23, 0, 0, tzinfo=TEHRAN))
        # آبان ۱۴۰۵ سی روز دارد؛ پایان = ۰۰:۰۰ اول آذر (۲۲ نوامبر ۲۰۲۶)
        self.assertEqual(end, dt.datetime(2026, 11, 22, 0, 0, tzinfo=TEHRAN))
        last_second = dt.datetime(2026, 11, 21, 23, 59, 59, tzinfo=TEHRAN)
        next_midnight = dt.datetime(2026, 11, 22, 0, 0, 0, tzinfo=TEHRAN)
        self.assertTrue(start <= last_second < end)
        self.assertFalse(start <= next_midnight < end)
        self.assertFalse(start <= start - dt.timedelta(seconds=1) < end)

    def test_esfand_range_respects_leap_year(self):
        s, e = ju.jalali_month_range_bounds(1404, 12, 12, TEHRAN)
        self.assertEqual((e - s).days, 29)
        s, e = ju.jalali_month_range_bounds(1403, 12, 12, TEHRAN)
        self.assertEqual((e - s).days, 30)

    def test_reversed_months_rejected(self):
        with self.assertRaises(ju.JalaliDateError):
            ju.jalali_month_range_bounds(1405, 8, 7)


class BirthdayPolicyTests(SimpleTestCase):
    def test_regular_birthday(self):
        born = dt.date(1991, 8, 14)  # 1370/05/23
        self.assertEqual(ju.birthday_month_day(born), (5, 23))
        self.assertEqual(ju.birthday_occurrence(born, 1405), ju.jalali_to_gregorian(1405, 5, 23))

    def test_esfand_30_moves_to_29_in_non_leap_year(self):
        born = ju.jalali_to_gregorian(1403, 12, 30)  # leap-year birthday
        self.assertEqual(ju.birthday_month_day(born), (12, 30))
        # 1404 is non-leap → Esfand 29
        self.assertEqual(ju.birthday_occurrence(born, 1404), ju.jalali_to_gregorian(1404, 12, 29))
        # 1403 is leap → Esfand 30 itself
        self.assertEqual(ju.birthday_occurrence(born, 1403), ju.jalali_to_gregorian(1403, 12, 30))

    def test_month_day_keys_include_1230_on_esfand_29_non_leap(self):
        self.assertEqual(ju.month_day_keys_for_date(ju.jalali_to_gregorian(1404, 12, 29)), [1229, 1230])
        self.assertEqual(ju.month_day_keys_for_date(ju.jalali_to_gregorian(1403, 12, 29)), [1229])
        self.assertEqual(ju.month_day_keys_for_date(ju.jalali_to_gregorian(1403, 12, 30)), [1230])

    def test_key(self):
        self.assertEqual(ju.birthday_month_day_key(None), None)
        self.assertEqual(ju.birthday_month_day_key(dt.date(1991, 8, 14)), 523)
