"""Проверки очистки и суточной агрегации на небольших искусственных данных."""

import unittest
from io import StringIO

import pandas as pd

from prepare import FIELDS, clean, summarize


def clean_rows(*rows):
    header = ";".join(["Date", "Time", *FIELDS])
    return clean(StringIO("\n".join([header, *rows])))


class CleaningTests(unittest.TestCase):
    def test_duplicate_minute_keeps_agreement_and_marks_conflict(self):
        minutes, quality = clean_rows(
            "01/01/2024;12:00:00;3;0;240;13;?;0;8",
            "01/01/2024;12:00:00;3;0;240;13;2;0;8",
            "01/01/2024;12:01:00;2;0;240;13;1;0;8",
            "01/01/2024;12:01:00;3;0;240;13;1;0;8",
        )
        self.assertEqual(len(minutes), 2)
        self.assertEqual(quality["extra_duplicate_rows"], 2)
        self.assertEqual(quality["conflicting_duplicate_cells"], 1)
        self.assertEqual(minutes.iloc[0]["sub_1_wh"], 2)
        self.assertTrue(pd.isna(minutes.iloc[1]["active_kw"]))
        self.assertEqual(minutes.iloc[1]["voltage_v"], 240)
        self.assertAlmostEqual(summarize(minutes).iloc[0]["observed_kwh"], 3 / 60)

    def test_corrupt_readings_and_physically_consistent_peak(self):
        minutes, quality = clean_rows(
            "01/01/2024;12:00:00;11;0;240;50;0;0;0",
            "01/01/2024;12:01:00;11;0;240;5;0;0;0",
            "01/01/2024;12:02:00;0;broken;0;0;-1;inf;?",
        )
        self.assertEqual(quality["inconsistent_active_minutes"], 1)
        self.assertEqual(quality["invalid_numeric_cells"], 4)
        self.assertEqual(minutes.iloc[0]["active_kw"], 11)
        self.assertTrue(pd.isna(minutes.iloc[1]["active_kw"]))
        self.assertEqual(minutes.iloc[2]["active_kw"], 0)
        self.assertTrue(minutes.iloc[2][["reactive_power", "voltage_v",
                                         "sub_1_wh", "sub_2_wh", "sub_3_wh"]].isna().all())


class DailyTests(unittest.TestCase):
    def test_complete_empty_and_partial_days(self):
        full_day = pd.date_range("2024-01-01", periods=1440, freq="min")
        index = full_day.append(pd.DatetimeIndex(["2024-01-03 12:00"]))
        minutes = pd.DataFrame({"active_kw": [2.0] * 1440 + [0.0]}, index=index)
        daily = summarize(minutes)
        self.assertEqual(daily["valid_minutes"].tolist(), [1440, 0, 1])
        full, empty, partial = daily.iloc[0], daily.iloc[1], daily.iloc[2]
        self.assertEqual(full["full_day_kwh"], 48)
        self.assertEqual(full["coverage_pct"], 100)
        self.assertTrue(pd.isna(empty["observed_kwh"]))
        self.assertTrue(pd.isna(empty["full_day_kwh"]))
        self.assertEqual(partial["observed_kwh"], 0)
        self.assertTrue(pd.isna(partial["full_day_kwh"]))
        self.assertAlmostEqual(partial["coverage_pct"], 100 / 1440)


if __name__ == "__main__":
    unittest.main()
