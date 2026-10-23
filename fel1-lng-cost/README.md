# FEL1 LNG Cost

A free tool that gives a first capital cost range for an LNG plant, early in a project (FEL1, concept stage). It works from past projects whose costs are public. These past projects are called **analogues**.

It covers four kinds of facility:

- Onshore liquefaction plants
- Floating liquefaction (FLNG)
- Onshore regasification (import) terminals
- Floating storage and regasification units (FSRU)

You enter the size of your plant, the year, and a few method choices. The tool returns a P10, P50 and P90 cost in US dollars, shows how each analogue led to its number, and exports the result to Excel.

> **Use with care.** This is a screening estimate (AACE Class 5). It is good for comparing options and checking whether an idea is worth more study. It is not a budget and must not be used for an investment decision.

## Quick start

You need Python 3.10 or newer.

```bash
cd fel1-lng-cost
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens the form. Fill in the sidebar from top to bottom, then read the result and download the Excel workbook.

To use it from Python instead, see `examples/example_estimate.py`.

## How it works

For each analogue the tool does four things:

1. **Escalate** the cost from its own year to your year. By default it adds 3% a year. You can upload a cost index instead.
2. **Relocate** it. You give a location factor for each region and for your site. Leave them all at 1.00 for no adjustment.
3. **Scale** it to your size with the exponent rule: cost = analogue cost × (your size ÷ analogue size)^0.7. Bigger plants cost less per tonne.
4. **Weight** it. An analogue the same size as yours counts fully. One twice or half your size counts half.

The P50 is the weighted middle of these numbers. The P10 and P90 come from their spread, but are never narrower than the accuracy band you choose (default -30% and +50%).

[METHODOLOGY.md](METHODOLOGY.md) explains each step, its formula and its limits.

## The public analogues

`data/public_analogues.csv` holds 24 projects. Every row links to its source. Unit costs are as reported, before escalation.

| Type | Projects | Cost years | Notes |
|---|---|---|---|
| Onshore liquefaction | 15 | 2013 to 2025 | Mostly US Gulf Coast. Five include upstream or are unclear and are left out by default. |
| FLNG | 4 | 2017 to 2025 | Two are FLNG units only (conversions). Two include subsea wells or are unclear. |
| Onshore regas | 4 | 2007 to 2017 | Netherlands, France, India, Singapore. |
| FSRU | 1 | 2022 | Shipyard price for the vessel only. |

Important points about this data:

- **Scope differs.** Some figures include a pipeline, financing costs or upstream fields. The `scope` and `notes` columns say what each one covers. By default the tool uses only "plant only" and "plant plus pipeline" rows.
- **Figures are announced costs**, mostly at the final investment decision. Final costs are often higher.
- **Few regas, FLNG and FSRU projects.** Treat those results with extra caution, or add your own.
- **Exchange rates** for the euro and Singapore dollar rows are approximate yearly averages. Check them if they matter to you.

## Adding your own projects

1. Copy `data/analogue_template.csv`.
2. Name the copy so it starts with `private_`, for example `private_my_projects.csv`.
3. Fill in one row per project. Use the same codes as the public file for `facility_type` and `scope`.
4. Load it in the web form (sidebar, step 2) or in Python with `load_analogues("private_my_projects.csv")`.

Files starting with `private_` are ignored by git, so they are never uploaded to GitHub. If your row has the same `id` as a public row, your row replaces it.

## Files

| Path | What it is |
|---|---|
| `app.py` | The web form |
| `fel1_lng_cost/analogues.py` | Loads and checks analogue data |
| `fel1_lng_cost/estimate.py` | The estimating method |
| `fel1_lng_cost/export.py` | Excel export |
| `data/public_analogues.csv` | Public analogue projects with sources |
| `data/analogue_template.csv` | Blank row for your own projects |
| `examples/example_estimate.py` | A worked example in Python |
| `tests/` | Automatic checks. Run `pytest` |

## Limits

- It knows only what the analogues know. A plant unlike any of them (very small, very cold site, unusual gas) needs a different approach.
- Escalation at a constant rate is rough over long periods. A cost index is better.
- The size exponent is a rule of thumb. Number of trains, modular design and site works all change the real answer.
- Location factors are your judgement. The tool does not supply them.

## Licence

MIT. You may use, change and share it, including for paid work, as long as you keep the copyright notice. See [LICENSE](../LICENSE).
