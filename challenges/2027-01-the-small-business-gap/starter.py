"""Starter for AI & the Economy, January 2027: The small-business gap.

Uses the tidy data files in this repo, so there's nothing to download first:

    pip install -r requirements.txt
    python challenges/2027-01-the-small-business-gap/starter.py

Want the very latest figures? Run `python data/fetch.py` first.

It prints a short summary and saves two charts, drawn with bezel-charts:

    small-firms.svg     AI use among businesses with fewer than 10 staff, every wave since 2023
    sizes-now.svg       AI use for every size of business in the latest wave
"""

from pathlib import Path

import pandas as pd

import bezel_charts as bc

ROOT = Path(__file__).resolve().parents[2]
SIZES = ["0 to 9", "10 to 49", "50 to 99", "100 to 249", "250 or more"]


def main() -> None:
    use = pd.read_csv(ROOT / "data" / "ai_use.csv")
    sizes = use[use["group_type"] == "size"].pivot(index="date", columns="group", values="using_ai").sort_index()
    sizes.index = pd.to_datetime(sizes.index).strftime("%b %Y")  # "2026-09" -> "Sep 2026"

    first, latest = sizes.index[0], sizes.index[-1]
    small, large = sizes["0 to 9"], sizes["250 or more"]
    print(f"Share of businesses using AI, {first} to {latest}")
    print(f"Fewer than 10 staff:  {small.iloc[0]:.1f}% then, {small.iloc[-1]:.1f}% now")
    print(f"250 or more staff:    {large.iloc[0]:.1f}% then, {large.iloc[-1]:.1f}% now")
    print(f"Gap in points:        {large.iloc[0] - small.iloc[0]:.1f} then, {large.iloc[-1] - small.iloc[-1]:.1f} now")

    # Beginner: one size band over time.
    bc.line(small.tolist(), labels=list(small.index), heading="Small firms using AI, % (fewer than 10 staff)",
            suffix="%", theme="light", width=720).save("small-firms.svg")

    # Intermediate idea: every size band side by side, in the latest wave.
    bc.bars(sizes.loc[latest, SIZES], heading=f"Businesses using AI by number of staff, {latest}",
            suffix="%", decimals=1, show_values=True, theme="light", width=720).save("sizes-now.svg")

    print("Saved small-firms.svg and sizes-now.svg. Open them in your browser.")


if __name__ == "__main__":
    main()
