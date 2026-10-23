"""Example: a 12 mtpa onshore liquefaction plant, in 2026 US dollars.

Run from the fel1-lng-cost folder:
    python examples/example_estimate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fel1_lng_cost import EstimateBasis, estimate, load_analogues, to_excel_file  # noqa: E402

# 1. Load the public analogues. To add your own, pass the file:
#    load_analogues("private_my_projects.csv")
analogues = load_analogues()

# 2. Describe the project and the method choices.
basis = EstimateBasis(
    facility_type="onshore_liquefaction",
    capacity_mtpa=12.0,
    estimate_year=2026,
    escalation_rate=0.03,      # 3% a year
    scale_exponent=0.7,        # cost grows with size to the power 0.7
    target_location_factor=1.0,
)

# 3. Run it and print the result.
result = estimate(analogues, basis)
print(result.summary())
print()
print(result.analogues[["project", "estimate_usd_million", "weight_share"]].round(2).to_string(index=False))

# 4. Save a workbook for the client.
out = to_excel_file(result, "example_estimate.xlsx")
print(f"\nSaved {out}")
