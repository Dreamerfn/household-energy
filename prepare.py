"""Очистка минутных измерений UCI и построение суточной таблицы."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "data" / "raw" / "household_power_consumption.txt"
FIELDS = {
    "Global_active_power": "active_kw",
    "Global_reactive_power": "reactive_power",
    "Voltage": "voltage_v",
    "Global_intensity": "current_a",
    "Sub_metering_1": "sub_1_wh",
    "Sub_metering_2": "sub_2_wh",
    "Sub_metering_3": "sub_3_wh",
}
POWER_TOLERANCE_KW = 0.10
MINUTES_PER_DAY = 1440


def clean(source):
    raw = pd.read_csv(source, sep=";", usecols=["Date", "Time", *FIELDS],
                      na_values=["?"], low_memory=False)
    stamp = pd.to_datetime(raw.pop("Date") + " " + raw.pop("Time"),
                           format="%d/%m/%Y %H:%M:%S", errors="coerce")
    on_minute = stamp.notna() & stamp.dt.second.eq(0)
    quality = {"source_rows": len(raw), "invalid_time_rows": int((~on_minute).sum())}
    raw = raw.loc[on_minute].rename(columns=FIELDS)
    raw.index = pd.DatetimeIndex(stamp[on_minute], name="timestamp")
    if raw.empty:
        raise ValueError("В файле нет корректных минутных меток.")

    quality["missing_input_cells"] = int(raw.isna().sum().sum())
    values = raw.apply(pd.to_numeric, errors="coerce")
    invalid = (values.isna() & raw.notna()) | values.lt(0) | values.eq(float("inf"))
    invalid["voltage_v"] |= values["voltage_v"].eq(0)
    quality["invalid_numeric_cells"] = int(invalid.sum().sum())
    values = values.mask(invalid)

    # Повтор одной минуты не должен удваивать расход.
    repeats = values.index.duplicated(keep=False)
    quality["extra_duplicate_rows"] = len(values) - values.index.nunique()
    quality["conflicting_duplicate_cells"] = 0
    if repeats.any():
        groups = values.loc[repeats].groupby(level=0)
        conflict = groups.nunique().gt(1)
        quality["conflicting_duplicate_cells"] = int(conflict.sum().sum())
        values = pd.concat([values.loc[~repeats], groups.first().mask(conflict)])

    apparent_kw = values["voltage_v"] * values["current_a"] / 1000
    spikes = values["active_kw"].gt(apparent_kw + POWER_TOLERANCE_KW)
    quality["inconsistent_active_minutes"] = int(spikes.sum())
    values.loc[spikes, "active_kw"] = float("nan")
    return values.sort_index(), quality


def summarize(minutes):
    by_day = minutes["active_kw"].resample("D")
    daily = by_day.count().rename("valid_minutes").to_frame()
    daily["coverage_pct"] = 100 * daily["valid_minutes"] / MINUTES_PER_DAY
    daily["observed_kwh"] = by_day.sum(min_count=1) / 60
    daily["full_day_kwh"] = daily["observed_kwh"].where(
        daily["valid_minutes"].eq(MINUTES_PER_DAY)
    )
    daily.index = daily.index.strftime("%Y-%m-%d").rename("day")
    return daily


def prepare(source, output):
    minutes, quality = clean(source)
    daily = summarize(minutes)
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as folder:
        pending = Path(folder)
        minutes.to_csv(pending / "minutes.csv", chunksize=50000)
        daily.to_csv(pending / "daily.csv", float_format="%.8f")
        pd.Series(quality, name="count").rename_axis("metric").to_csv(pending / "quality.csv")
        for file in pending.iterdir():
            file.replace(output / file.name)
    return daily, quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=DEFAULT_SOURCE,
                        help="Исходный TXT или ZIP с одним TXT")
    parser.add_argument("--output", type=Path, default=ROOT / "data", help="Папка для CSV")
    args = parser.parse_args()
    try:
        daily, quality = prepare(args.source, args.output)
    except (OSError, ValueError, BadZipFile) as exc:
        parser.exit(1, f"Не удалось подготовить данные. {exc}\n")
    print(f"CSV сохранены в {args.output}")
    print(f"Исходных строк {quality['source_rows']:,}. Дней {len(daily)}. "
          f"Полных дней {daily['full_day_kwh'].count()}.")


if __name__ == "__main__":
    main()
