"""How the charts in this brief were made. They're a snapshot of the data at launch, so the brief and its
numbers always agree. Run from the repository root:

    python challenges/2027-01-the-small-business-gap/make_charts.py
"""

import random
from pathlib import Path

import pandas as pd

import bezel_charts as bc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

random.seed(2026)  # stable gradient ids, so rerunning gives identical files
use = pd.read_csv(ROOT / "data" / "ai_use.csv")
sizes = use[use["group_type"] == "size"].pivot(index="date", columns="group", values="using_ai").sort_index()
labels = [""] + [pd.Timestamp(d + "-01").strftime("%b %Y") for d in sizes.index[1:]]

bc.line({"Fewer than 10 staff": sizes["0 to 9"].tolist(), "10 to 49 staff": sizes["10 to 49"].tolist(),
         "250 or more staff": sizes["250 or more"].tolist()},
        labels=labels, heading="Share of businesses using AI, by number of staff", suffix="%", zero=True,
        theme="light", width=760, height=240).save(HERE / "size-over-time.svg")

gap = (sizes["250 or more"] - sizes["0 to 9"]).round(1)
bc.line(gap.tolist(), labels=labels, heading="The gap: largest firms minus smallest, percentage points",
        decimals=1, zero=True, theme="light", width=760, height=200).save(HERE / "gap-in-points.svg")

print("Saved the brief's charts to", HERE)
