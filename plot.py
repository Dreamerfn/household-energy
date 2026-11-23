"""График суточного потребления электроэнергии за выбранные даты."""

import argparse
from datetime import date
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


def draw(days, output, show):
    start, end = days.index[0].date(), days.index[-1].date()
    fig, (energy, coverage) = plt.subplots(
        2, 1, sharex=True, figsize=(10, 5.6), height_ratios=[3, 1], layout="constrained"
    )
    fig.suptitle(f"Потребление электроэнергии домохозяйством\n{start:%d.%m.%Y} — {end:%d.%m.%Y}")
    energy.plot(days.index, days["full_day_kwh"], color="#176D79", lw=1.3,
                marker="o", ms=3, label="Полные сутки")
    partial = days.loc[days["valid_minutes"].between(1, 1439)]
    energy.scatter(partial.index, partial["observed_kwh"], color="#BD541D", marker="^",
                   s=35, label="Измерено за неполные сутки", zorder=3)
    energy.set_ylabel("Расход, кВт·ч")
    energy.set_ylim(bottom=0)
    energy.legend(loc="upper right", frameon=False)
    if days["observed_kwh"].isna().all():
        energy.text(0.5, 0.45, "За выбранные даты показаний нет",
                    transform=energy.transAxes, ha="center")

    coverage.bar(days.index, days["coverage_pct"], color="#587A9A", width=0.85)
    coverage.set(ylim=(0, 105), yticks=[0, 50, 100], ylabel="Покрытие, %", xlabel="Дата")
    margin = pd.Timedelta(hours=16)
    coverage.set_xlim(days.index[0] - margin, days.index[-1] + margin)
    if len(days) <= 8:
        coverage.set_xticks(days.index)
        coverage.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    else:
        locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
        coverage.xaxis.set_major_locator(locator)
        coverage.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%y"))
    for axis in (energy, coverage):
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
        output = ROOT / "plots" / f"energy_{start}_{end}.png"
        measured = days["observed_kwh"].sum(min_count=1)
        if pd.notna(measured):
            print(f"За минуты с показаниями измерено {measured:.3f} кВт·ч.")
        print(f"Полных суток {days['full_day_kwh'].count()} из {len(days)}.")
        draw(days, output, show=not args.no_show)
        print(f"График сохранён в {output}")
    except FileNotFoundError:
        parser.exit(1, f"Файл {args.data} не найден. Укажите --data или запустите prepare.py.\n")
    except (OSError, ValueError, KeyError, EOFError) as exc:
        parser.exit(1, f"Не удалось построить график. {exc}\n")


if __name__ == "__main__":
    main()
