# FEL1 LNG Cost

A free tool for a first capital cost estimate of an LNG liquefaction plant, at FEL 1 (concept stage). It works from past projects with published costs, called **analogs**.

The tool follows the [FEL 1 LNG Capital Cost Estimating Guideline v0.1](docs/GUIDELINE.md). The guideline has 13 steps. In each step, every method choice is a **switch** with options, a default and a source. You can change any switch. The tool records every switch, defaults included, in a **decision log**.

> **Use with care.** The result is an AACE Class 5 estimate: good for screening ideas, comparing concepts and supporting a Gate 1 decision. It is not a budget, and it must not be used for an investment decision. The range is a set of reasoned bounds, not a statistical P10 and P90.

## What it covers

| Facility | Status |
|---|---|
| Onshore liquefaction | Full method, all 13 steps |
| FLNG, onshore regas terminals, FSRUs | Preview. The guideline does not cover these yet. The tool runs the shared steps and switches off the liquefaction-only factors. |

## Quick start

You need Python 3.10 or newer.

```bash
cd fel1-lng-cost
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens the app.

1. Fill in **Step 1** in the sidebar: purpose, train size, number of trains, site type and location.
2. Read the **Result** tab.
3. Review the switches in **Method switches**, the weights in **Analogs and weights**, and add site items in **Site items**. Give a reason for each change.
4. Download the Excel workbook.

To use it from Python, see `examples/example_estimate.py`. It compares a greenfield plant with a brownfield variant.

## How the tool follows the guideline

| Step | What the tool does |
|---|---|
| 1. Key inputs | Purpose, capacity per train and train count, site type, location, date, feed gas, process family, battery limits, accuracy target. |
| 2. Analog selection | Filters on facility type, train size band (0.5 to 2 times), FID date (last 15 years), scope, site type, size cluster and process family. Every analog filtered out shows the reason. Warns below 5 analogs; stops below 3. |
| 3. Adjustment method | Multiply (default), or hybrid: storage and marine are taken out of the analogs and added back as the target's own blocks. |
| 4. Escalation | Constant rate, cost index, damped index, or two cases. With an index loaded, the default runs two cases: full index (high) and half the index change (low). Shows the calibration pairs that test the damping fraction. |
| 5. Location | OIES location groups (USA 1.00 to NW Australia 1.72), with steps of 0.10. Optionally applies the factor to the construction share only (32%). |
| 6. Scope and complexity | Plant-only splits, owner's costs on EPC-only figures, site type to greenfield, multi-train to one train, gas complexity (simple or graded), CO2 sequestration. |
| 7. Size scaling | Unit cost × (target train ÷ analog train)^(n − 1), n = 0.7. Always shows n = 0.6 and 0.8. Reports a fitted n but does not use it unless you ask. Three methods for multi-train targets. |
| 8. Combining | Rubric points for each analog, your weight (1, 2 or 3) with a reason where it differs, outlier flags, and weighted mean, simple mean and median side by side. |
| 9. Site items | A register of site items. Each one is added to the base, carried as a risk or opportunity, or noted, by the guideline's decision tree and materiality threshold. Helpers for tanks and dredging. |
| 10. Variants | Other methods for the same option, the rule for choosing the base, and a block-by-block brownfield method. |
| 11. Cost blocks | By cost type (OIES) and by area. Items outside the battery limits are removed by block. |
| 12. Range | Built from the escalation cases, the analog spread, definition growth and site risks, then checked against the class band. Contingency only for the share of weight not on sanctioned budgets. Correlated comparison of two options. |
| 13. Outputs | Summary, analog journey table and chart, escalation chart, size curve, weights panel, cost blocks, risk register, range chart, sensitivities, decision log, references, and an Excel workbook with all of them. |

`fel1_lng_cost/factors.py` lists every default with its source. Defaults that rest on judgment say so.

## The public analogs

`data/public_analogs.csv` holds 45 projects. Every row has a source link and a note on what the figure covers.

| Facility | Projects | FID years | With a plant-only split |
|---|---|---|---|
| Onshore liquefaction | 31 | 2007 to 2025 | 21 |
| FLNG | 9 | 2011 to 2025 | 5 |
| Onshore regas | 4 | 2007 to 2017 | 0 |
| FSRU | 1 | 2022 | 0 |

Most onshore projects come from Appendix 1 of the OIES paper the guideline cites (Songhurst, 2018). It gives a total cost and a liquefaction-only cost for each project. Newer projects (Rio Grande, Port Arthur, Louisiana LNG, Nigeria LNG Train 7 and others) come from company releases.

Each row records the guideline's Step 2 fields: project, country, site type, trains, train size, FID year, published figure, currency, what the figure covers, contingency status, source and a data quality grade (A, B or C).

Points to know:

- **Money year.** For OIES figures that are final or latest costs, the money year is the middle of construction. This is a judgment, noted in each row.
- **Location groups and steps** for each analog follow the guideline's step rule. Judgment calls are noted in the row.
- **Site type.** Liquefaction added to an existing import terminal is treated as brownfield, as OIES does. Donggi-Senoro and LNG Canada are treated as partly brownfield (built on existing industrial sites).
- **Process family, FID year and contractor** are from public record, not always from the cost source. Rows marked "check" deserve a second look.
- **Exchange rates** for the euro and Singapore dollar rows are approximate yearly averages.

## Adding your own analogs

1. Copy `data/analog_template.csv`.
2. Name the copy so it starts with `private_`, for example `private_my_projects.csv`.
3. Fill in one row per project, with the same codes as the public file.
4. Load it in the app (Analogs and weights tab) or in Python with `load_analogs("private_my_projects.csv")`.

Git ignores files that start with `private_`, so they never reach GitHub. A row with the same `id` as a public row replaces it.

## Loading a cost index

CEPCI and the S&P Global indices are copyrighted, so the tool cannot ship them. If you hold one, fill in `data/cost_index_template.csv` (columns `year` and `index`), save it as `private_cost_index.csv`, and load it in the Method switches tab, Step 4. The tool then runs the two default escalation cases.

## Files

| Path | What it is |
|---|---|
| `app.py` | The web app |
| `fel1_lng_cost/factors.py` | Every default and its source |
| `fel1_lng_cost/basis.py` | Step 1 inputs, every switch, and the decision log |
| `fel1_lng_cost/estimate.py` | Steps 2 to 12 |
| `fel1_lng_cost/export.py` | Excel workbook |
| `fel1_lng_cost/charts.py` | Charts for the app |
| `data/public_analogs.csv` | Public analogs with sources |
| `data/analog_template.csv` | Blank row for your own analogs |
| `data/cost_index_template.csv` | Blank cost index |
| `docs/GUIDELINE.md` | The estimating guideline |
| `examples/example_estimate.py` | Greenfield against brownfield, in Python |
| `tests/` | Automatic checks. Run `pytest` |

## Known limits

These come from the guideline (Section 19), plus a few of the tool's own.

- Location factors and the escalation case move every analog together. They are the largest judgments, so the tool always shows their sensitivity.
- Public figures rarely state their full scope. Read each source before using a number.
- Most figures are announced at FID. Final costs are often higher.
- OIES factors reflect 2014 to 2018 conditions and a limited project set.
- The estimate date is a year, not a quarter.
- Probabilistic ranging (Step 12, option D) is for FEL 2 and is not built.
- The tool sets no location factor of its own beyond the OIES groups and the step rule.

## Licence

MIT. You may use, change and share it, including for paid work, as long as you keep the copyright notice. See [LICENSE](../LICENSE).
