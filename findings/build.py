"""Draw every chart and write the findings report from the latest data.

Run from the repository root after data/fetch.py:

    python findings/build.py

Charts go into charts/ as SVG files, made with bezel-charts (https://pypi.org/project/bezel-charts/).
The report is written to findings/README.md, and the headline tiles and key findings in the main README
are rewritten between their marker comments. Every number is worked out from the data, so it stays true
when ONS publishes new figures. Nothing in them is typed in by hand.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

import bezel_charts as bc

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHARTS = ROOT / "charts"
REPORT = ROOT / "findings" / "README.md"
README = ROOT / "README.md"

THEME = {"theme": "light"}
WIDE = 760

# ONS industry names are long. These are the plain-English labels used on the charts.
INDUSTRIES = {
    "Information and communication": "Tech, media and telecoms",
    "Professional, scientific and technical activities": "Professional and scientific",
    "Arts, entertainment and recreation": "Arts and entertainment",
    "Education": "Education",
    "Administrative and support service activities": "Admin and support services",
    "Wholesale and retail trade; repair of motor vehicles and motorcycles": "Wholesale and retail",
    "Manufacturing": "Manufacturing",
    "Accommodation and food service activities": "Hotels, pubs and restaurants",
    "Real estate activities": "Property",
    "Transportation and storage": "Transport and storage",
    "Construction": "Construction",
    "Human health and social work activities": "Health and social care",
    "Other service activities": "Other services",
    "Water supply, sewerage, waste management and remediation activities": "Water and waste",
}
SIZES = ["0 to 9", "10 to 49", "50 to 99", "100 to 249", "250 or more"]

# Barriers, in ONS's words cut down to plain English. ONS has reworded the list over time, so only the
# answers offered in the latest wave are charted.
BARRIERS = {
    "lack_of_expertise": "Not enough AI expertise",
    "lack_of_trust": "Don't trust AI is safe or transparent",
    "cost": "Cost",
    "security": "Security concerns",
    "no_clear_use": "Can't see how to use it",
    "environmental_impact": "Environmental impact",
    "regulation_concerns": "Rules and regulation",
    "staff_concerns": "Staff are worried",
    "availability": "Can't get the right product",
}


# Loading -------------------------------------------------------------------------------------

def load() -> tuple[dict, dict]:
    names = ["ai_use", "ai_plans", "ai_barriers", "ai_extent", "ai_adoption_route", "ai_headcount", "ai_by_region"]
    data = {name: pd.read_csv(DATA / f"{name}.csv") for name in names}
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    return data, sources


def every_business(table: pd.DataFrame) -> pd.DataFrame:
    """The all-business rows, one per wave, oldest first."""
    return table[table["group_type"] == "all"].sort_values("date").set_index("date")


def wave(table: pd.DataFrame, date: str, kind: str) -> pd.Series:
    """One wave's figures for every industry or size band, keyed by group."""
    rows = table[(table["date"] == date) & (table["group_type"] == kind)]
    return rows.set_index("group")


# Words for dates and changes --------------------------------------------------------------------

def mon(date: str) -> str:
    """'2026-09' -> 'Sep 2026'."""
    return pd.Timestamp(date + "-01").strftime("%b %Y")


def month_name(date: str) -> str:
    """'2026-09' -> 'September 2026'."""
    return pd.Timestamp(date + "-01").strftime("%B %Y")


def pts(change: float) -> str:
    change = round(change, 1)
    if change == 0:
        return "unchanged"
    return f"{'up' if change > 0 else 'down'} {abs(change):.1f} points"


def lc(text: str) -> str:
    """Lower-case a label for use mid-sentence, keeping words like AI in capitals."""
    return " ".join(w if w.isupper() and len(w) > 1 else w.lower() for w in text.split())


def save(chart: bc.Chart, name: str) -> str:
    CHARTS.mkdir(exist_ok=True)
    chart.save(CHARTS / f"{name}.svg")
    return f"../charts/{name}.svg"


def axis(labels: list[str]) -> list[str]:
    """Labels for a line chart. The first one is left blank: bezel-charts 1.0 pins it to the left edge,
    where it can run into the next label."""
    return [""] + labels[1:]


# The findings --------------------------------------------------------------------------------

def headline_tiles(d: dict) -> dict:
    """The headline numbers: three small tiles with the latest figure and every wave behind it."""
    use, plans = every_business(d["ai_use"]), every_business(d["ai_plans"])
    big = d["ai_use"][d["ai_use"]["group"] == "250 or more"].sort_values("date").set_index("date")
    tiles = [
        ("using", use["using_ai"], "Businesses using AI"),
        ("large", big["using_ai"], "Large firms using AI"),
        ("planning", plans["planning_ai"], "Planning to adopt AI"),
    ]
    out = {}
    for slug, s, heading in tiles:
        s = s.dropna()
        # The change label would read "▲ 20.3%", which looks like a 20% rise when it's 20.3 points, so it's
        # switched off, as in the sister projects. The report gives the change in points underneath.
        chart = bc.spark(s.tolist(), labels=[mon(t) for t in s.index], heading=heading, suffix="%", decimals=1,
                         delta="none", width=300, **THEME)
        out[slug] = save(chart, f"tile-{slug}")
    return out


def over_time(d: dict) -> dict:
    """Finding 1: how fast AI use has spread, against the businesses that haven't even tried it."""
    use, bars_ = every_business(d["ai_use"]), every_business(d["ai_barriers"])
    both = pd.concat({"use": use["using_ai"], "untried": bars_["not_attempted"]}, axis=1).dropna()
    chart = bc.line({"Using AI": both["use"].tolist(), "Haven't tried AI": both["untried"].tolist()},
                    labels=axis([mon(t) for t in both.index]), heading="Share of UK businesses",
                    suffix="%", zero=True, width=WIDE, height=240, **THEME)
    crossed = next((t for t in both.index if both.loc[t, "use"] > both.loc[t, "untried"]), None)
    first, last = use.index[0], use.index[-1]
    year_ago = use.index[-5] if len(use) >= 5 else first
    tech = {"text_generation_llm": "writing text with tools like ChatGPT", "visual_content": "creating images and video",
            "data_processing_ml": "analysing data with machine learning", "image_processing_ml": "recognising images",
            "robotics": "robotics"}
    latest_tech = use.loc[last, list(tech)].dropna().sort_values(ascending=False)
    extent = every_business(d["ai_extent"]).iloc[-1]
    route = every_business(d["ai_adoption_route"]).iloc[-1]
    plans = every_business(d["ai_plans"])["planning_ai"]
    return {"chart": save(chart, "ai-use-over-time"), "first": first, "last": last,
            "start": float(use.loc[first, "using_ai"]), "now": float(use.loc[last, "using_ai"]),
            "year_ago": (year_ago, float(use.loc[year_ago, "using_ai"])),
            "untried_start": float(both["untried"].iloc[0]), "untried_now": float(both["untried"].iloc[-1]),
            "crossed": crossed, "tech": [(tech[k], float(v)) for k, v in latest_tech.items()],
            "llm_start": float(use.loc[first, "text_generation_llm"]),
            "extensive": float(extent["extensively"]), "limited": float(extent["limited_basis"]),
            "extent_when": extent.name, "free": float(route["free_software"]), "bought": float(route["bought_software"]),
            "in_house": float(route["built_in_house"]), "plans": float(plans.iloc[-1]), "plans_start": float(plans.iloc[0])}


def sectors(d: dict) -> dict:
    """Finding 2: which industries use AI, then and now."""
    use = d["ai_use"]
    first, last = sorted(use["date"].unique())[0], sorted(use["date"].unique())[-1]
    now = wave(use, last, "industry")["using_ai"].dropna()
    then = wave(use, first, "industry")["using_ai"]
    both = pd.DataFrame({"then": then.reindex(now.index), "now": now}).dropna().sort_values("now", ascending=False)
    labels = [INDUSTRIES.get(i, i) for i in both.index]
    chart = bc.bars({f"{mon(first)}": both["then"].tolist(), f"{mon(last)}": both["now"].tolist()},
                    labels=labels, horizontal=True, heading="Share of businesses using AI, by industry",
                    suffix="%", decimals=1, width=WIDE, **THEME)
    growth = (both["now"] - both["then"]).sort_values(ascending=False)
    uk = float(every_business(use).loc[last, "using_ai"])
    return {"chart": save(chart, "ai-use-by-industry"), "both": both, "first": first, "last": last, "uk": uk,
            "growth": growth, "short": INDUSTRIES}


def sizes(d: dict) -> dict:
    """Finding 3: big firms against small firms."""
    use, bars_ = d["ai_use"], d["ai_barriers"]
    first, last = sorted(use["date"].unique())[0], sorted(use["date"].unique())[-1]
    then = wave(use, first, "size")["using_ai"].reindex(SIZES)
    now = wave(use, last, "size")["using_ai"].reindex(SIZES)
    chart = bc.bars({mon(first): then.tolist(), mon(last): now.tolist()},
                    labels=[f"{s} staff" for s in SIZES], heading="Share of businesses using AI, by number of staff",
                    suffix="%", decimals=1, show_values=True, width=WIDE, height=230, **THEME)
    barriers = wave(bars_, last, "size").reindex(SIZES)
    return {"chart": save(chart, "ai-use-by-size"), "then": then, "now": now, "first": first, "last": last,
            "barriers": barriers}


def regions(d: dict) -> dict:
    """Finding 4: where in the UK. Unweighted, so regions are compared with each other only."""
    r = d["ai_by_region"].set_index("region")
    places = r.drop(index=[i for i in ("UK", "England") if i in r.index])["using_ai"].dropna().sort_values(ascending=False)
    middle = float(places.median())
    inner = places.iloc[1:-1]
    chart = bc.bars(places, horizontal=True, heading="Share of surveyed businesses using AI, by nation and region",
                    suffix="%", decimals=1, goal=middle, width=WIDE, **THEME)
    return {"chart": save(chart, "ai-use-by-region"), "places": places, "median": middle, "inner": (len(inner), float(inner.max() - inner.min())), "when": r["date"].iloc[0],
            "england": float(r.loc["England", "using_ai"]) if "England" in r.index else None}


def barriers(d: dict) -> dict:
    """Finding 5: what's holding businesses back now, and how that has changed."""
    b = every_business(d["ai_barriers"])
    last, first = b.index[-1], b.index[0]
    now = b.loc[last, [k for k in BARRIERS if k in b.columns]].dropna().sort_values(ascending=False)
    chart = bc.bars(pd.Series(now.values, index=[BARRIERS[k] for k in now.index]), horizontal=True,
                    heading=f"Share of all businesses held back by each reason, {month_name(last)}",
                    suffix="%", decimals=1, width=WIDE, **THEME)
    tracked = [k for k in ("cost", "lack_of_expertise", "security", "no_clear_use", "staff_concerns")
               if pd.notna(b.loc[first, k]) and pd.notna(b.loc[last, k])]
    change = {k: (float(b.loc[first, k]), float(b.loc[last, k])) for k in tracked}
    any_barrier = 100 - float(b.loc[last, "not_attempted"]) - float(b.loc[last, "no_barriers"]) - float(b.loc[last, "not_sure"])
    any_start = 100 - float(b.loc[first, "not_attempted"]) - float(b.loc[first, "no_barriers"]) - float(b.loc[first, "not_sure"])
    trust = b["lack_of_trust"].dropna() if "lack_of_trust" in b.columns else pd.Series(dtype=float)
    return {"chart": save(chart, "ai-barriers"), "now": now, "first": first, "last": last, "change": change,
            "trust_from": trust.index[0] if len(trust) else None,
            "names": BARRIERS, "untried": (float(b.loc[first, "not_attempted"]), float(b.loc[last, "not_attempted"])),
            "any": any_barrier, "any_start": any_start}


def headcount(d: dict) -> dict:
    """Bonus: what AI has done to jobs at the businesses using it."""
    h = every_business(d["ai_headcount"])
    last = h.index[-1]
    added = h["increased"].dropna()
    use = every_business(d["ai_use"])
    # The headcount question goes to businesses using AI or not sure if they are: everyone except "don't use".
    asked = 100 - float(use.loc[last, "not_using"]) if last in use.index else None
    return {"when": last, "first": h.index[0], "reduced": float(h.loc[last, "reduced"]),
            "no_change": float(h.loc[last, "no_change"]), "added_now": h.loc[last, "increased"],
            "added_last": (added.index[-1], float(added.iloc[-1])) if len(added) else None,
            "reduced_first": float(h["reduced"].iloc[0]), "asked": asked}


# The report ----------------------------------------------------------------------------------

TILES = [("using", "Share of UK businesses using AI"), ("large", "Share of firms with 250 or more staff using AI"),
         ("planning", "Share of businesses planning to adopt AI in the next three months")]


def tile_row(tiles: dict, base: str = "../") -> str:
    """The three tiles side by side. Fixed pixel widths, which GitHub keeps on one row."""
    imgs = "\n".join(f'  <img src="{base}{tiles[key].removeprefix("../")}" width="270" alt="{alt}, every survey since 2023">'
                     for key, alt in TILES)
    return f'<p align="center">\n{imgs}\n</p>'


CREDIT = (
    "Charts are drawn with [bezel-charts](https://pypi.org/project/bezel-charts/), an open-source Python library "
    "created by Shaz Moghaddam, the author of this project."
)


def short(name: str, s: dict) -> str:
    return s["short"].get(name, name)


def low(name: str, s: dict) -> str:
    return lc(short(name, s))


def write_report(f: dict, sources: dict) -> str:
    t, ot, sec, sz, rg, br, hc = (f[k] for k in ("tiles", "time", "sectors", "sizes", "regions", "barriers", "jobs"))
    last = ot["last"]
    both = sec["both"]
    top, bottom = both.index[0], both.index[-1]
    growth = sec["growth"]
    fastest = growth.index[0]
    small, large = float(sz["now"]["0 to 9"]), float(sz["now"]["250 or more"])
    small0, large0 = float(sz["then"]["0 to 9"]), float(sz["then"]["250 or more"])
    places = rg["places"]
    spread_regions = float(places.iloc[0] - places.iloc[-1])
    spread_sectors = float(both["now"].iloc[0] - both["now"].iloc[-1])
    spread_sizes = large - small
    sb = sz["barriers"]
    top_barrier = br["now"].index[0]
    second_barrier = br["now"].index[1]
    low_start = both[both["then"] < 5].sort_values("now", ascending=False)
    catch_up = ", ".join(f"{low(i, sec)} ({both.loc[i, 'then']:.1f}% to {both.loc[i, 'now']:.1f}%)" for i in low_start.index[:3])
    catch_line = (f"- Industries that barely used AI in {sec['first'][:4]} have moved, from a very low start: {catch_up}.\n"
                  if len(low_start) else "")
    crossed_line = (
        f"In **{month_name(ot['crossed'])}**, for the first time, more businesses were using AI than said they hadn't even "
        f"tried it."
        if ot["crossed"] else ""
    )
    tech_lines = "\n".join(f"  - {name}: **{share:.1f}%**" for name, share in ot["tech"][:4])
    all_grew = all(b > a for a, b in br["change"].values())
    change_intro = (f"Since {mon(br['first'])}, every barrier ONS has asked about the whole time has grown:" if all_grew else
                    f"Here's how the barriers ONS has asked about the whole time have changed since {mon(br['first'])}:")
    now_b = br["now"]
    if "lack_of_trust" in now_b and "cost" in now_b and br["trust_from"]:
        verb = "more often than" if now_b["lack_of_trust"] > now_b["cost"] + 0.5 else "about as often as" if abs(now_b["lack_of_trust"] - now_b["cost"]) <= 0.5 else "less often than"
        trust_line = (f"Not trusting AI to be safe or transparent is now mentioned {verb} cost. ONS only started asking about "
                      f"trust in {month_name(br['trust_from'])}, so it can't be compared further back.")
    else:
        trust_line = ""
    change_lines = "\n".join(
        f"- **{br['names'][k]}**: {a:.1f}% to **{b:.1f}%**" for k, (a, b) in
        sorted(br["change"].items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True)
    )
    added = hc["added_now"]
    if pd.notna(added):
        added_line = f"**{added:.1f}%** added staff"
    elif hc["added_last"]:
        added_line = (f"too few added staff for ONS to publish a figure (it was {hc['added_last'][1]:.1f}% in "
                      f"{month_name(hc['added_last'][0])})")
    else:
        added_line = "too few added staff for ONS to publish a figure"
    gap_then, gap_now = large0 - small0, large - small
    gap_ratio_then, gap_ratio_now = large0 / small0, large / small
    london_line = ""
    if "London" in places.index:
        rank = list(places.index).index("London") + 1
        london_line = (f"London is {'top' if rank == 1 else f'number {rank}'} at **{places['London']:.1f}%**. "
                       "That probably reflects what the industry figures show: London has more tech, media and professional "
                       "firms than anywhere else, and those are the heaviest AI users. ")

    return f"""# State of AI in UK business

**Latest data: {month_name(last)}.** Every number and chart on this page is worked out from ONS data by
[`build.py`](build.py), and redrawn automatically when ONS publishes new figures. {CREDIT}

Data from the ONS Business Insights and Conditions Survey, wave {sources['wave']}, released {sources['released']}.
Last downloaded: {sources['fetched']}.

## The headline numbers

{tile_row(t)}

Each tile shows every survey since {mon(ot['first'])}. The big number is the latest figure.

- **{ot['now']:.1f}%** of UK businesses use at least one AI technology, {pts(ot['now'] - ot['year_ago'][1])} on a year earlier.
- Among firms with **250 or more staff**, it's **{large:.1f}%**, up from {large0:.1f}% in {mon(ot['first'])}.
- **{ot['plans']:.1f}%** say they plan to adopt AI in the next three months, against {ot['plans_start']:.1f}% in {mon(ot['first'])}.
  Some already use it and plan to add more.

## 1. How fast is AI spreading?

![Share of businesses using AI, and share that haven't tried it]({ot['chart']})

When ONS first asked, in {month_name(ot['first'])}, **{ot['start']:.1f}%** of UK businesses used any kind of AI.
By {month_name(last)} it was **{ot['now']:.1f}%**: {ot['now'] / ot['start']:.1f} times as many in three years.

Over the same time the share of businesses that said they **hadn't even tried** AI fell from
**{ot['untried_start']:.1f}%** to **{ot['untried_now']:.1f}%**.{(" " + crossed_line) if crossed_line else ""}

- The most common use, by far, is writing text with large language models like ChatGPT. What businesses use now:
{tech_lines}
- Writing text with AI went from {ot['llm_start']:.1f}% of businesses to {ot['tech'][0][1]:.1f}%. Most of the growth is
  everyday tools, not robots or self-driving vans.
- **Most use is light.** Of businesses using AI, only **{ot['extensive']:.1f}%** say they use it extensively. **{ot['limited']:.1f}%**
  use it on a limited basis.
- **Most AI is bought or free, not built.** {ot['bought']:.1f}% of AI users bought ready-made software and {ot['free']:.1f}% use
  free tools. Only {ot['in_house']:.1f}% built anything themselves.

So AI has gone mainstream in three years, but for most businesses it's a handy tool on the side, not something
the business runs on. Each wave is a survey with some sampling noise, so a small dip from one wave to the next means little. It's the trend that counts.

## 2. Which industries are using it?

![AI use by industry, then and now]({sec['chart']})

The gap between industries is huge. In {month_name(last)}, **{sec['both']['now'].iloc[0]:.1f}%** of
{low(top, sec)} businesses used AI, against **{sec['both']['now'].iloc[-1]:.1f}%** in
{low(bottom, sec)}. The UK average was {sec['uk']:.1f}%.

- **{short(fastest, sec)}** grew most, {pts(growth[fastest])} since {mon(sec['first'])}.
{catch_line}- **Health and social care** stays near the bottom at {both['now'].get('Human health and social work activities', float('nan')):.1f}%, even though it's
  one of the areas where people talk most about what AI could do. Much of the work is hands-on and closely
  regulated, which may slow things down.
- **Construction and transport** are also well below average. A lot of their work is physical, where chatbots
  and image tools are less obviously useful.

These are private businesses. BICS doesn't cover the public sector, so "education" here means private schools,
colleges and training firms, not state schools. Industry figures come from smaller samples, so they move around
more from one wave to the next.

## 3. Big firms against small firms

![AI use by business size, then and now]({sz['chart']})

The bigger the business, the more likely it is to use AI. In {month_name(last)}, **{large:.1f}%** of firms with 250 or
more staff used it, against **{small:.1f}%** of the smallest firms, with fewer than 10 staff.

Is the gap closing? It depends how you measure it.

- **In proportion, yes.** Big firms were {gap_ratio_then:.1f} times as likely as the smallest to use AI in
  {mon(sz['first'])}. Now it's {gap_ratio_now:.1f} times.
- **In points, no.** The gap has grown from {gap_then:.1f} points to **{gap_now:.1f} points**, because big firms
  added {large - large0:.1f} points while small ones added {small - small0:.1f}.

Most UK businesses are tiny, so the smallest firms set the national figure. That's why the UK average sits
close to the 0 to 9 staff number.

Bigger firms also report more barriers, partly because more of them are actually trying. In {month_name(sz['last'])},
**{sb.loc['250 or more', 'lack_of_expertise']:.1f}%** of the largest firms said a lack of AI expertise had held them back,
against {sb.loc['0 to 9', 'lack_of_expertise']:.1f}% of the smallest. Only {sb.loc['250 or more', 'not_attempted']:.1f}% of the largest
firms hadn't tried AI at all, against {sb.loc['0 to 9', 'not_attempted']:.1f}% of the smallest.

## 4. Where in the UK?

![AI use by nation and region]({rg['chart']})

{london_line}It's lowest in **{places.index[-1]} ({places.iloc[-1]:.1f}%)**. The line marks the middle region, {rg['median']:.1f}%.

But the most striking thing is how **close** the regions are. Leaving the top and bottom aside, the other
{rg['inner'][0]} are within **{rg['inner'][1]:.1f} points** of each other. The spread between regions is {spread_regions:.1f} points. Between
industries it's {spread_sectors:.1f} points, and between the smallest and largest firms {spread_sizes:.1f} points.
**What a business does, and how big it is, matter far more than where it is.**

**Read these regional figures with care.** ONS only publishes them as a share of the businesses that answered,
without the weighting used for the UK, industry and size figures. The businesses that answer lean towards bigger
firms, and a business counts in every region it trades in, so the regional numbers run higher than the UK figure of {ot['now']:.1f}%. They're
fine for comparing regions with each other, not for comparing with the rest of this page. These are for
{month_name(rg['when'])} only.

## 5. What's holding businesses back?

![What's stopping businesses adopting AI]({br['chart']})

ONS asks every business what, if anything, has stopped or delayed them adopting AI in the last three months.
The top reasons in {month_name(br['last'])} were **{lc(br['names'][top_barrier])}** ({br['now'].iloc[0]:.1f}%)
and **{lc(br['names'][second_barrier])}** ({br['now'].iloc[1]:.1f}%).

The bigger story is how the answers have changed. In {month_name(br['first'])} the most common answer by far was
"we haven't tried": **{br['untried'][0]:.1f}%**. Now it's **{br['untried'][1]:.1f}%**. More businesses have had a go, and more
of them have hit something. The share naming at least one barrier went from about {br['any_start']:.0f}% to {br['any']:.0f}%.

{change_intro}

{change_lines}

The concerns have moved from "is this for us?" towards **"can we trust it, and is it safe?"**. {trust_line}

## What about jobs?

Since {month_name(hc['first'])}, ONS has asked businesses that use AI what it has done to their headcount.

- In {month_name(hc['when'])}, **{hc['no_change']:.1f}%** said no change, **{hc['reduced']:.1f}%** said they'd cut staff and
  {added_line}.
- So among AI users, cuts outnumber hires. But the numbers are small. The question goes to the {hc['asked']:.0f}% of
  businesses that use AI or aren't sure, so about {hc['reduced'] * (hc['asked'] or 0) / 100:.1f}% of all UK
  businesses say AI has led them to cut staff so far.

This is one to watch. The sister project, [Jobs & the Economy](https://github.com/ShazMoghaddam/uk-jobs-economy), tracks
the wider jobs market.

---

**Source:** Office for National Statistics, Business Insights and Conditions Survey (BICS), under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
Details of every file are in [`data/sources.json`](../data/sources.json).
"""


def key_findings(f: dict) -> str:
    """The four strongest findings for the front page, with numbers from the latest data."""
    ot, sec, sz, br = f["time"], f["sectors"], f["sizes"], f["barriers"]
    chart = lambda path: path.removeprefix("../")  # noqa: E731
    both = sec["both"]
    small, large = float(sz["now"]["0 to 9"]), float(sz["now"]["250 or more"])
    crossed = (f" Since {month_name(ot['crossed'])}, more businesses use AI than say they haven't tried it."
               if ot["crossed"] else "")
    gap_now = large - small
    gap_then = float(sz["then"]["250 or more"]) - float(sz["then"]["0 to 9"])
    size_heading = "Big firms are pulling ahead" if gap_now > gap_then else "Big firms lead, but the gap is closing"
    size_line = (f"The gap has grown to {gap_now:.1f} points." if gap_now > gap_then else
                 f"The gap is down to {gap_now:.1f} points, from {gap_then:.1f}.")
    word = {"lack_of_expertise": "Skills", "lack_of_trust": "Trust", "cost": "Cost", "security": "Security",
            "no_clear_use": "Finding a use", "environmental_impact": "The environment", "regulation_concerns": "Regulation",
            "staff_concerns": "Staff worries", "availability": "Availability"}
    first_two = [word.get(k, k) for k in br["now"].index[:2]]
    barrier_heading = f"{first_two[0]} and {first_two[1].lower()} are now the biggest barriers"
    return f"""### {ot['now'] / ot['start']:.0f} times as many businesses use AI as in {ot['first'][:4]}

**{ot['now']:.1f}%** of UK businesses used AI in {month_name(ot['last'])}, up from {ot['start']:.1f}% in {month_name(ot['first'])}.{crossed}
Most of it is light use of everyday tools like ChatGPT.

![AI use over time]({chart(ot['chart'])})

### It depends what you do

**{both['now'].iloc[0]:.1f}%** of {low(both.index[0], sec)} businesses use AI, against **{both['now'].iloc[-1]:.1f}%**
in {low(both.index[-1], sec)}.

![AI use by industry]({chart(sec['chart'])})

### {size_heading}

**{large:.1f}%** of firms with 250 or more staff use AI, against {small:.1f}% of those with fewer than 10. {size_line}

![AI use by size]({chart(sz['chart'])})

### {barrier_heading}

Firms that haven't tried AI fell from {br['untried'][0]:.1f}% to {br['untried'][1]:.1f}%. Now the biggest things holding
businesses back are **{lc(br['names'][br['now'].index[0]])}** and **{lc(br['names'][br['now'].index[1]])}**.

![What's holding businesses back]({chart(br['chart'])})"""


def update_readme(f: dict) -> None:
    """Rewrite the generated parts of the main README, between their marker comments."""
    text = README.read_text(encoding="utf-8")
    blocks = {"tiles": tile_row(f["tiles"], base=""), "key-findings": key_findings(f)}
    for name, body in blocks.items():
        start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
        if start not in text or end not in text:
            raise RuntimeError(f"README.md is missing the {start} ... {end} markers")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = f"{before}{start}\n{body}\n{end}{after}"
    README.write_text(text, encoding="utf-8")


def main() -> None:
    # bezel-charts gives each gradient a random id so charts can share a page. A fixed seed keeps the
    # files identical from one run to the next, so only real changes in the data show up in git.
    random.seed(2026)
    data, sources = load()
    findings = {
        "tiles": headline_tiles(data),
        "time": over_time(data),
        "sectors": sectors(data),
        "sizes": sizes(data),
        "regions": regions(data),
        "barriers": barriers(data),
        "jobs": headcount(data),
    }
    REPORT.write_text(write_report(findings, sources), encoding="utf-8")
    update_readme(findings)
    print(f"Saved {len(list(CHARTS.glob('*.svg')))} charts to {CHARTS}, the report to {REPORT}, and updated {README}")


if __name__ == "__main__":
    main()
