"""Checks that the data is complete and the report says nothing silly.

Run from the repository root with `pytest`. The refresh workflow runs these before opening a pull request,
so a broken download or an odd ONS release never reaches the README unnoticed.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SERIES = ["ai_use", "ai_plans", "ai_barriers", "ai_extent", "ai_adoption_route", "ai_headcount"]


@pytest.fixture(scope="module")
def sources() -> dict:
    return json.loads((DATA / "sources.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def use() -> pd.DataFrame:
    return pd.read_csv(DATA / "ai_use.csv")


@pytest.fixture(scope="module")
def report() -> str:
    return (ROOT / "findings" / "README.md").read_text(encoding="utf-8")


def test_every_file_is_listed_and_present(sources):
    for name in SERIES + ["ai_by_region"]:
        assert name in sources["files"], name
        assert (DATA / f"{name}.csv").exists(), name


def test_every_file_reaches_the_latest_wave(sources):
    latest = pd.read_csv(DATA / "ai_use.csv")["wave"].max()
    assert latest == sources["wave"]
    for name in SERIES:
        table = pd.read_csv(DATA / f"{name}.csv")
        assert table["wave"].max() == latest, f"{name} stops at wave {table['wave'].max()}"
        assert not table.duplicated(["wave", "group"]).any(), f"{name} has a group twice in one wave"


def test_every_wave_has_all_businesses_and_every_size_band(use):
    for wave, rows in use.groupby("wave"):
        groups = set(rows["group"])
        assert "All businesses" in groups, wave
        assert {"0 to 9", "10 to 49", "50 to 99", "100 to 249", "250 or more"} <= groups, wave


def test_values_are_percentages(sources):
    for name in SERIES + ["ai_by_region"]:
        table = pd.read_csv(DATA / f"{name}.csv")
        numbers = table.select_dtypes("number").drop(columns=["wave"], errors="ignore")
        assert ((numbers >= 0) & (numbers <= 100) | numbers.isna()).all().all(), name


def test_using_ai_matches_the_ons_definition(use):
    """Using AI is everyone except 'don't use' and 'not sure', and it can't be less than any one technology."""
    techs = ["text_generation_llm", "visual_content", "data_processing_ml", "image_processing_ml"]
    rows = use.dropna(subset=["using_ai", "not_using", "not_sure"])
    assert (abs(rows["using_ai"] - (100 - rows["not_using"] - rows["not_sure"])) < 0.051).all()
    biggest = rows[techs].max(axis=1).fillna(0)  # a row where ONS hid every technology has nothing to check
    # ONS rounds each answer separately, so using_ai (worked out from two rounded numbers) can come out a
    # tenth of a point below one technology. Anything more than that would be a real problem.
    assert (rows["using_ai"] + 0.15 >= biggest).all()


def test_headline_is_believable(use):
    every = use[use["group"] == "All businesses"].sort_values("date")
    assert every["using_ai"].between(1, 90).all()
    # Large firms have been ahead of the smallest in every wave so far. If that ever flips, it's a story
    # worth a human look before it's published, not a quiet change in the report.
    large = use[use["group"] == "250 or more"].set_index("wave")["using_ai"]
    small = use[use["group"] == "0 to 9"].set_index("wave")["using_ai"]
    assert (large > small).all()


def test_regions_are_all_there():
    regions = pd.read_csv(DATA / "ai_by_region.csv")
    assert {"London", "Scotland", "Wales", "Northern Ireland", "North East", "South West"} <= set(regions["region"])
    assert regions["using_ai"].notna().sum() >= 12


def test_report_is_fully_filled_in(report):
    assert "{" not in report and "}" not in report, "a placeholder was left unfilled"
    for bad in ("nan", "NaN", "None", "inf", "NaT"):
        assert not re.search(rf"\b{bad}\b", report), f"report contains {bad!r}"
    assert "—" not in report, "no em dashes in the report"
    assert " ai " not in report, "AI should always be in capitals"


def test_every_chart_in_the_report_exists(report):
    charts = re.findall(r"\.\./charts/([\w-]+\.svg)", report)
    assert len(charts) >= 8
    for name in charts:
        svg = (ROOT / "charts" / name).read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "No data yet" not in svg, name


def test_readme_generated_blocks_are_filled_in():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in ("tiles", "key-findings"):
        block = readme.split(f"<!-- {name}:start -->")[1].split(f"<!-- {name}:end -->")[0]
        assert len(block.strip()) > 100, f"the {name} block in README.md is empty"
        assert "{" not in block and not re.search(r"\b(nan|None|NaT)\b", block), name
    for name in re.findall(r"\(charts/([\w-]+\.svg)\)|src=\"charts/([\w-]+\.svg)\"", readme):
        assert (ROOT / "charts" / (name[0] or name[1])).exists(), name


def test_no_em_dashes_anywhere():
    for path in list(ROOT.glob("*.md")) + list(ROOT.glob("challenges/**/*.md")) + list(ROOT.glob("findings/*.md")):
        assert "—" not in path.read_text(encoding="utf-8"), path.name
