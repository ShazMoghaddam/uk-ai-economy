"""Download the UK business AI data this project uses, straight from the ONS.

Run from the repository root:

    python data/fetch.py            # only rewrites the files if there's a newer AI wave
    python data/fetch.py --force    # rewrites them anyway

The figures come from the ONS Business Insights and Conditions Survey (BICS), which asks thousands of
UK businesses about trading conditions every two weeks. Every sixth wave, roughly once a quarter, it
also asks about artificial intelligence. Each new BICS spreadsheet carries the full AI history back to
September 2023, so this script finds the newest wave that has the AI questions and reads it.

It writes these files into data/:

    ai_use.csv          which AI technologies businesses use, by industry and size, every AI wave
    ai_plans.csv        which AI technologies businesses plan to adopt in the next three months
    ai_barriers.csv     what has stopped or delayed businesses from adopting AI
    ai_extent.csv       how deeply businesses that use AI rely on it
    ai_adoption_route.csv  how businesses that use AI got it: built, bought, outsourced or free tools
    ai_headcount.csv    what AI has done to headcount, at businesses that use it
    ai_by_region.csv    AI use by nation and region, latest wave (see the note on regions below)
    sources.json        what each file is, where it came from and when ONS released it

Everything is free under the Open Government Licence v3.0. Only the Python standard library, pandas
and openpyxl are needed.

A few notes on the data:

- Values are percentages of businesses, rounded to one decimal place as ONS publishes them.
- Blank cells are either hidden by ONS to protect confidentiality ([c] in the spreadsheet) or the
  question didn't offer that answer in that wave ([x]).
- The UK, industry and size figures are weighted by ONS to represent all UK businesses. The regional
  figures are not: ONS only publishes them as a share of the businesses that answered, and a business
  counts in every region it trades in. They're good for comparing regions with each other, not for
  comparing with the weighted UK figure.
- `date` is the month the survey ran, e.g. "2026-09" for 21 September to 4 October 2026. The exact
  dates are in the `period` column.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ONS = "https://www.ons.gov.uk"
HERE = Path(__file__).resolve().parent
USER_AGENT = "uk-ai-economy (+https://github.com/ShazMoghaddam/uk-ai-economy)"
DATASET = "/economy/economicoutputandproductivity/output/datasets/businessinsightsandimpactontheukeconomy"

# How far back to look for a wave with the AI questions. They're asked every sixth wave, so eight is plenty.
MAX_FILES = 8

# file name: (sheet in the BICS spreadsheet, what it holds, who was asked)
SHEETS = {
    "ai_use": ("AI Current Usage TS (WTD)", "Which AI technologies businesses currently use",
               "Businesses not permanently stopped trading"),
    "ai_plans": ("AI Plan to Adopt TS (WTD)", "Which AI technologies businesses plan to adopt in the next three months",
                 "Businesses not permanently stopped trading"),
    "ai_barriers": ("AI Prevent or Delayed TS (WTD)",
                    "Factors that prevented or delayed AI adoption in the last three months",
                    "Businesses not permanently stopped trading"),
    "ai_extent": ("AI Extent Use TS (WTD)", "How much businesses use AI in their operations",
                  "Businesses using AI, or not sure if they are"),
    "ai_adoption_route": ("AI How Adopted TS (WTD)", "How businesses adopted the AI they use",
                          "Businesses using AI, or not sure if they are"),
    "ai_headcount": ("AI Impact on Headcount TS (WTD)", "What AI has done to the business's overall headcount",
                     "Businesses using AI, or not sure if they are"),
}
REGION_SHEET = "Artificial Intelligence (1)"

# ONS answer text -> short column name. Anything not listed gets a tidy version of its own text.
COLUMNS = {
    "Autonomous vehicles": "autonomous_vehicles",
    "Data processing using machine learning": "data_processing_ml",
    "Image processing using machine learning": "image_processing_ml",
    "Robotics": "robotics",
    "Text generation using Large Language Models": "text_generation_llm",
    "Visual content creation": "visual_content",
    "Other": "other",
    "Not sure": "not_sure",
    "Not applicable": "not_applicable",
    "Business does not currently use artificial intelligence technologies": "not_using",
    "Business does not plan to adopt artificial intelligence technologies in the next three months": "no_plans",
    # Barriers
    "Concerns about environmental impact": "environmental_impact",
    "Concerns about government regulations or industry standards": "regulation_concerns",
    "Uncertainty about government regulations or industry standards": "regulation_uncertainty",
    "Cost": "cost",
    "High costs or lack of access to finance": "cost_or_finance",
    "Difficulty identifying business use cases": "no_clear_use",
    "No identified use case for artificial intelligence technology": "no_use_case_found",
    "Employee concern about any potential impact of using artificial intelligence technologies": "staff_concerns",
    "Employee concerns about job security or workload": "staff_job_concerns",
    "Lack of trust in artificial intelligence technology product safety or transparency": "lack_of_trust",
    "Level of expertise in artificial intelligence": "lack_of_expertise",
    "Limited artificial intelligence technology skills, expertise, or knowledge": "limited_skills",
    "Product or service availability": "availability",
    "Security concerns": "security",
    "Technical integration or scalability challenges": "integration",
    "Business has not attempted to use artificial intelligence technologies": "not_attempted",
    "Business has not been prevented or experienced delays in the adoption of artificial intelligence technologies": "no_barriers",
    # Extent
    "Used extensively": "extensively",
    "Used on a limited basis": "limited_basis",
    "Used only for artificial intelligence technology testing or pilots": "testing_only",
    "Not currently used": "not_currently_used",
    # Adoption route
    "Developed in-house": "built_in_house",
    "Outsourced to external providers or third parties": "outsourced",
    "Through purchase of external software or ready-to-use systems": "bought_software",
    "Using free-to-use software": "free_software",
    # Headcount
    "Increased headcount": "increased",
    "No change": "no_change",
    "Reduced headcount": "reduced",
}

SIZE_BANDS = {"0 - 9": "0 to 9", "10 - 49": "10 to 49", "50 - 99": "50 to 99", "100 - 249": "100 to 249",
              "250 +": "250 or more", "All size bands excluding 0 - 9": "10 or more", "All businesses": "All businesses"}


def get(url: str, retries: int = 3) -> bytes:
    """Fetch a URL politely, retrying a couple of times if ONS is busy."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception:  # noqa: BLE001 - any network hiccup gets a retry
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def column(text: str) -> str:
    """A short column name for an ONS answer. ONS sometimes tweaks the wording between waves, so a known
    answer also matches if the first 30 characters agree."""
    text = " ".join(str(text).split())
    if text in COLUMNS:
        return COLUMNS[text]
    for known, name in COLUMNS.items():
        if len(text) >= 30 and known[:30].lower() == text[:30].lower():
            return name
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def percent(value) -> float | None:
    """ONS gives shares like 0.103. Turn them into 10.3, and anything hidden or not asked into a blank."""
    if isinstance(value, (int, float)) and not pd.isna(value):
        return round(float(value) * 100, 1)
    return None


def month(period: str) -> str:
    """'21 September 2026 to 4 October 2026' -> '2026-09', the month the survey started."""
    start = period.split(" to ")[0].strip()
    if not re.search(r"\d{4}$", start):  # '18 September to 1 October 2023'
        start = f"{start} {period.strip()[-4:]}"
    return pd.to_datetime(start, format="%d %B %Y").strftime("%Y-%m")


def read_series(book: bytes, sheet: str) -> pd.DataFrame:
    """One of BICS's weighted time series sheets as a tidy table: one row per wave and group."""
    raw = pd.read_excel(io.BytesIO(book), sheet_name=sheet, header=None)
    header = raw.index[raw[0].astype(str).str.strip().eq("Dates")][0]
    table = raw.iloc[header + 1:].copy()
    table.columns = [str(c).strip() for c in raw.iloc[header]]
    table = table[table["Wave"].astype(str).str.startswith("Wave")]
    out = pd.DataFrame({
        "date": table["Dates"].map(month),
        "wave": table["Wave"].str.extract(r"(\d+)")[0].astype(int),
        "period": table["Dates"].str.strip(),
    })
    group = table["Industry/Size Band"].astype(str).str.strip()
    out["group_type"] = group.map(lambda g: "all" if g == "All businesses" else "size" if g in SIZE_BANDS else "industry")
    out["group"] = group.map(lambda g: SIZE_BANDS.get(g, g))
    for name in table.columns[3:]:
        if name and name != "nan":
            out[column(name)] = table[name].map(percent)
    out = out.dropna(axis=1, how="all")
    return out.sort_values(["date", "group_type", "group"]).reset_index(drop=True)


def read_regions(book: bytes) -> pd.DataFrame:
    """The first table on the regional AI sheet: AI use by region, unweighted, latest wave only."""
    raw = pd.read_excel(io.BytesIO(book), sheet_name=REGION_SHEET, header=None)
    period = re.search(r"UK, (.+)$", str(raw.iloc[1, 0])).group(1)
    header = raw.index[raw[0].astype(str).str.strip().eq("Region")][0]
    rows = []
    for i in range(header + 1, len(raw)):
        name = raw.iloc[i, 0]
        if not isinstance(name, str) or not name.strip():
            break
        row = {"region": name.strip()}
        for j, answer in enumerate(raw.iloc[header, 1:], start=1):
            if isinstance(answer, str):
                row[column(answer)] = percent(raw.iloc[i, j])
        rows.append(row)
    table = pd.DataFrame(rows)
    table.insert(0, "period", period)
    table.insert(0, "date", month(period))
    return table


def add_using_ai(table: pd.DataFrame) -> pd.DataFrame:
    """The ONS headline measure: the share using at least one AI technology. Everyone else either said
    they don't use AI or weren't sure, so it's 100 minus those two."""
    using = (100 - table["not_using"] - table["not_sure"]).round(1)
    table.insert(table.columns.get_loc("group" if "group" in table else "region") + 1, "using_ai", using)
    return table


def add_planning_ai(table: pd.DataFrame) -> pd.DataFrame:
    planning = (100 - table["no_plans"] - table["not_sure"]).round(1)
    table.insert(table.columns.get_loc("group") + 1, "planning_ai", planning)
    return table


def newest_ai_wave() -> tuple[bytes, str, str, str]:
    """Walk back from the newest BICS spreadsheet until one has the AI questions."""
    page = get(ONS + DATASET).decode("utf-8", "replace")
    links = list(dict.fromkeys(re.findall(r'href="(/file\?uri=[^"]+\.xlsx)"', page)))
    if not links:
        raise RuntimeError("Could not find any BICS spreadsheets on the ONS dataset page.")
    for link in links[:MAX_FILES]:
        wave = re.search(r"bicswave(\d+)", link)
        print(f"Checking wave {wave.group(1) if wave else '?'} for the AI questions...")
        book = get(ONS + link)
        names = pd.ExcelFile(io.BytesIO(book)).sheet_names
        if SHEETS["ai_use"][0] in names:
            released = re.search(r"Released (\d{1,2} \w+ \d{4})", str(pd.read_excel(io.BytesIO(book), sheet_name=0, header=None).iloc[:3, 0].tolist()))
            return book, ONS + link, wave.group(1) if wave else "", released.group(1) if released else ""
        time.sleep(0.5)
    raise RuntimeError(f"None of the newest {MAX_FILES} BICS spreadsheets had the AI questions.")


def already_have(wave: str) -> bool:
    """True if the files in data/ already come from this wave. Each wave's figures are final when ONS
    publishes them, so there's nothing to update until the next AI wave comes out."""
    manifest = HERE / "sources.json"
    if not manifest.exists() or not wave:
        return False
    return str(json.loads(manifest.read_text(encoding="utf-8")).get("wave")) == wave


def main() -> None:
    book, url, wave, released = newest_ai_wave()
    if already_have(wave) and "--force" not in sys.argv:
        print(f"Already up to date with BICS wave {wave}. Run with --force to download it again anyway.")
        return
    sources = {}
    for name, (sheet, description, base) in SHEETS.items():
        table = read_series(book, sheet)
        if name == "ai_use":
            table = add_using_ai(table)
        if name == "ai_plans":
            table = add_planning_ai(table)
        table.to_csv(HERE / f"{name}.csv", index=False)
        sources[name] = {"description": description, "base": base, "sheet": sheet, "weighted": True,
                         "first": table["date"].min(), "last": table["date"].max(), "waves": int(table["wave"].nunique())}
        print(f"Saved {name}.csv: {table['wave'].nunique()} waves, {len(table)} rows")

    regions = add_using_ai(read_regions(book))
    regions.to_csv(HERE / "ai_by_region.csv", index=False)
    sources["ai_by_region"] = {
        "description": "Which AI technologies businesses currently use, by nation and region",
        "base": "Businesses that answered and are not permanently stopped trading",
        "sheet": REGION_SHEET, "weighted": False,
        "note": "Unweighted, and a business counts in every region it trades in. Compare regions with each other, "
                "not with the weighted UK figures.",
        "first": regions["date"].iloc[0], "last": regions["date"].iloc[0], "waves": 1,
    }
    print(f"Saved ai_by_region.csv: {len(regions)} nations and regions")

    manifest = {
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "survey": "ONS Business Insights and Conditions Survey (BICS)",
        "wave": int(wave) if wave else None,
        "released": released,
        "file": url,
        "dataset": ONS + DATASET,
        "licence": "Open Government Licence v3.0",
        "credit": "Source: Office for National Statistics licensed under the Open Government Licence v3.0.",
        "files": sources,
    }
    (HERE / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Done. Data from BICS wave {wave}, released {released}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Download failed: {exc}\nONS may be busy. Wait a minute and run it again.")
