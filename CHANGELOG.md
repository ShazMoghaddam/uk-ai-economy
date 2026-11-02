# Changelog

All notable changes to this project are listed here. Data refreshes from the ONS aren't listed one by one; each
arrives as its own pull request from the Refresh data workflow.

Versions are dated by month, like `v2026.11`.

## Unreleased

- Social preview image in `assets/social-preview.png`, drawn from the real AI use figures, so shared links show a
  proper card

## v2026.11 · November 2026

The launch.

- **State of AI in UK business** report with five findings and a section on jobs, every number worked out from the
  data and redrawn when ONS publishes new figures
- Five charts and three headline tiles, all drawn with [bezel-charts](https://pypi.org/project/bezel-charts/)
- `data/fetch.py` downloads AI use, plans, barriers, depth of use, how AI was adopted, headcount and regional
  figures from the ONS Business Insights and Conditions Survey, back to September 2023
- First monthly challenge, January 2027: The small-business gap
- Checks on every pull request, a weekly data refresh that opens a pull request when a new AI wave is out,
  Dependabot, and contributing, submission and security guides
