"""График суточного потребления электроэнергии за выбранные даты."""

import argparse
from datetime import date, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parent


def choose_date(label, argument, first, last, default):
    while True:
        value = argument if argument is not None else input(
            f"{label} (ГГГГ-ММ-ДД, Enter = {default}): "
        ).strip()
        try:
            day = date.fromisoformat(value) if value else default
            if value and day.isoformat() != value:
                raise ValueError
            if first <= day <= last:
                return day
        except ValueError:
            pass
        message = f"{label}. Введите дату от {first} до {last} в формате ГГГГ-ММ-ДД."
        if argument is not None:
            raise ValueError(message)
        print(message)


def read_minutes(daily_path, start, end):
    source = daily_path.with_name("minutes.csv")
    if not source.exists():
        source = daily_path.with_name("minutes.zip")
    if not source.exists():
        raise ValueError("Рядом с суточным CSV нужен minutes.csv или minutes.zip.")
    first, stop = start.isoformat(), (end + timedelta(days=1)).isoformat()
    selected = []
    for chunk in pd.read_csv(source, usecols=["timestamp", "active_kw"], chunksize=100000):
        stamp = chunk["timestamp"]
        selected.append(chunk.loc[(stamp >= first) & (stamp < stop)])
    rows = pd.concat(selected, ignore_index=True)
    rows["timestamp"] = pd.to_datetime(rows["timestamp"])
    return rows.set_index("timestamp")["active_kw"].asfreq("min")


def draw(days, minutes, output, show):
    start, end = days.index[0], days.index[-1]
    fig, (power, energy) = plt.subplots(2, 1, figsize=(12, 6.5), height_ratios=[2, 1],
                                        layout="constrained")
    power.set_title(f"Потребление дома: {start:%d.%m.%Y} — {end:%d.%m.%Y}")
    power.plot(minutes, color="#90AEC9", lw=0.55, alpha=0.7, label="Минутные измерения")
    hours = minutes.resample("h")
    mean_kw = hours.mean().where(hours.count().eq(60))
    power.plot(mean_kw, color="#204E78", lw=1.7, marker=".", ms=2,
               label="Средняя мощность за час")
    power.set(ylabel="Активная мощность, кВт", ylim=(0, None),
              xlim=(start, end + pd.Timedelta(days=1)))
    power.legend(loc="upper right")
    if minutes.count() == 0:
        power.text(0.5, 0.45, "За выбранный период показаний нет",
                   transform=power.transAxes, ha="center")

    complete = days["full_day_kwh"].dropna()
    bars = energy.bar(complete.index, complete, width=0.65, color="#248878")
    if len(days) <= 21:
        energy.bar_label(bars, fmt="%.1f", padding=2, fontsize=9)
    if complete.empty:
        energy.text(0.5, 0.45, "За выбранный период нет полных суток",
                    transform=energy.transAxes, ha="center")
    energy.margins(y=0.16)
    margin = pd.Timedelta(hours=14)
    energy.set(title="Суточное потребление (только полные сутки)", ylabel="Энергия, кВт·ч",
               xlabel="Дата", ylim=(0, None), xlim=(start - margin, end + margin))
    for axis in (power, energy):
        if len(days) <= 10:
            axis.xaxis.set_major_locator(mdates.DayLocator())
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        else:
            axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=9))
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%y"))
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    if show:
        plt.show()
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="Первый день включительно, ГГГГ-ММ-ДД")
    parser.add_argument("--end", help="Последний день включительно, ГГГГ-ММ-ДД")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "daily.csv",
                        help="Суточный CSV из prepare.py")
    parser.add_argument("--no-show", action="store_true", help="Только сохранить PNG")
    args = parser.parse_args()
    try:
        daily = pd.read_csv(args.data, index_col="day", parse_dates=["day"]).sort_index()
        if daily.empty:
            raise ValueError("Суточная таблица пуста.")
        first, last = daily.index.min().date(), daily.index.max().date()
        print(f"Доступны даты с {first} по {last}.")
        start = choose_date("Начало", args.start, first, last, first)
        end = choose_date("Конец", args.end, start, last, last)
        days = daily.loc[str(start):str(end)]
        minutes = read_minutes(args.data, start, end)
        output = ROOT / "plots" / f"energy_{start}_{end}.png"
        measured = days["observed_kwh"].sum(min_count=1)
        if pd.notna(measured):
            print(f"За минуты с показаниями измерено {measured:.3f} кВт·ч.")
        print(f"Полных суток {days['full_day_kwh'].count()} из {len(days)}.")
        draw(days, minutes, output, show=not args.no_show)
        print(f"График сохранён в {output}")
    except FileNotFoundError:
        parser.exit(1, f"Файл {args.data} не найден. Укажите --data или запустите prepare.py.\n")
    except (OSError, ValueError, KeyError, EOFError) as exc:
        parser.exit(1, f"Не удалось построить график. {exc}\n")


if __name__ == "__main__":
    main()
