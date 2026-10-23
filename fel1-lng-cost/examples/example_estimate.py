"""Example: two 4.5 MTPA trains at a remote Southeast Asian site, greenfield
against a brownfield variant, in 2026 US dollars.

Run from the fel1-lng-cost folder:
    python examples/example_estimate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fel1_lng_cost import (  # noqa: E402
    BrownfieldShares, SiteItem, compare_options, estimate, load_analogs, make_basis, to_excel_file,
)

# 1. Analogs. Add your own with load_analogs("private_my_projects.csv").
analogs = load_analogs()

# 2. Step 1 inputs, plus the switches you want to change. Everything else is
#    the guideline default, and the decision log records it as such.
greenfield = make_basis(
    purpose="compare",
    train_size_mtpa=4.5,
    trains=2,
    site_type="greenfield",
    location_name="Example remote site",
    target_region="Southeast Asia",
    location_group="remote",   # OIES remote group, 1.30
    location_steps=-1,         # one step down: established industrial LNG site
    estimate_year=2026,
    site_items=[
        # Analogs carry a typical jetty, so only the difference travels, as a risk.
        SiteItem("Long trestle", "marine", analogs_carry_typical=True,
                 central=0, low=-100, high=250, driver="2.5 km trestle"),
    ],
    reasons={"step:1": "Example inputs", "step:5": "Established LNG region"},
    option_name="Greenfield",
)

# 3. A brownfield variant priced two ways (Step 10): the OIES factor, and
#    block by block from the greenfield blocks.
brownfield = greenfield.with_changes(
    site_type="brownfield",
    option_name="Brownfield",
    brownfield_shares=BrownfieldShares(utilities=0.4, site_works=0.2, storage_marine=0.0, tie_ins_musd=150),
    method_gap_note="Block method assumes the hub provides 60% of utilities; check with site data.",
)

a = estimate(analogs, greenfield)
b = estimate(analogs, brownfield)
print(a.summary(), "\n")
print(b.summary(), "\n")
print(b.methods[["name", "value", "judgment_calls", "chosen"]].round(0).to_string(index=False), "\n")

# 4. Compare the options with shared drivers held together (Step 12).
diff = compare_options(a, b)
print(f"Brownfield minus greenfield: {diff['central_difference']:,.0f} USD m "
      f"(correlated range {diff['low']:,.0f} to {diff['high']:,.0f})")

# 5. Save the workbook with every Step 13 output.
out = to_excel_file(b, "example_estimate.xlsx", comparison=diff)
print(f"\nSaved {out}")
