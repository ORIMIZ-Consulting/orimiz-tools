"""FEL1 (concept stage) capital cost estimate from analogue projects.

The method has four steps for each analogue, then one step to combine them.

1. Escalate. Bring the analogue cost from its own year to the estimate year:
       C_esc = C_analogue * escalation_factor(cost_year -> estimate_year)
   The factor comes either from a constant yearly rate or from a cost index
   table you supply (for example a published plant cost index).

2. Relocate. Remove the analogue's location effect and add the target's:
       C_loc = C_esc * (target_location_factor / analogue_location_factor)

3. Scale for size with the exponent ("six-tenths") rule:
       C_scaled = C_loc * (Q_target / Q_analogue) ** n
   n is below 1 because bigger plants cost less per tonne. Values of 0.6 to
   0.8 are common for process plants; this tool defaults to 0.7 for
   liquefaction and 0.6 for regasification. Change it if you have better data.

4. Weight. Analogues closer in size count more:
       w = (Q_small / Q_large)
   so an analogue the same size gets weight 1, and one twice or half the size
   gets weight 0.5.

5. Combine. The P50 is the weighted median of the analogue-based estimates.
   The range is the wider of two things:
   - the spread of the analogue-based estimates (weighted P10 and P90), and
   - the expected accuracy band for the estimate class. AACE International
     Recommended Practice 18R-97 gives Class 5 (concept screening) a low
     range of -20% to -50% and a high range of +30% to +100%. The default
     here is -30% and +50%; set your own.

This is a screening tool. It cannot replace a properly scoped estimate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .analogues import DEFAULT_SCOPES

DEFAULT_EXPONENTS = {
    "onshore_liquefaction": 0.7,
    "flng": 0.7,
    "onshore_regas": 0.6,
    "fsru": 0.6,
}

# Size ratios beyond this are flagged: the exponent rule gets less reliable.
MAX_SAFE_SIZE_RATIO = 3.0


@dataclass
class EstimateBasis:
    """Everything the estimate needs. Only the first two have no default."""

    facility_type: str
    capacity_mtpa: float
    estimate_year: int = 2026
    target_region: str = "Target"
    target_location_factor: float = 1.0
    # Factor for each analogue region, relative to the same base as the
    # target factor. Regions not listed use 1.0.
    region_location_factors: dict[str, float] = field(default_factory=dict)
    escalation_rate: float = 0.03
    # Optional {year: index value}. If given, it replaces escalation_rate
    # for years it covers; years outside it use escalation_rate.
    cost_index: dict[int, float] | None = None
    scale_exponent: float | None = None
    scopes: tuple[str, ...] = DEFAULT_SCOPES
    site_types: tuple[str, ...] | None = None
    exclude_ids: tuple[str, ...] = ()
    class_low: float = -0.30
    class_high: float = 0.50

    def exponent(self) -> float:
        if self.scale_exponent is not None:
            return self.scale_exponent
        return DEFAULT_EXPONENTS.get(self.facility_type, 0.7)


@dataclass
class EstimateResult:
    basis: EstimateBasis
    analogues: pd.DataFrame
    p10_usd_million: float
    p50_usd_million: float
    p90_usd_million: float
    analogue_p10_usd_million: float
    analogue_p90_usd_million: float
    warnings: list[str]

    @property
    def p50_unit_cost_usd_per_tpa(self) -> float:
        return self.p50_usd_million / self.basis.capacity_mtpa

    def summary(self) -> str:
        b = self.basis
        lines = [
            f"FEL1 estimate: {b.capacity_mtpa:g} mtpa {b.facility_type}, "
            f"{b.estimate_year} US dollars",
            f"  P10  {self.p10_usd_million:>10,.0f} million",
            f"  P50  {self.p50_usd_million:>10,.0f} million"
            f"   ({self.p50_unit_cost_usd_per_tpa:,.0f} USD per tonne per year)",
            f"  P90  {self.p90_usd_million:>10,.0f} million",
            f"  Based on {len(self.analogues)} analogues, scale exponent {b.exponent():g}",
        ]
        lines += [f"  Note: {w}" for w in self.warnings]
        return "\n".join(lines)


def escalation_factor(from_year: int, to_year: int, rate: float,
                      index: dict[int, float] | None = None) -> float:
    """Factor that moves a cost from one year's money to another's."""
    if index and from_year in index and to_year in index:
        return index[to_year] / index[from_year]
    return (1.0 + rate) ** (to_year - from_year)


def weighted_quantile(values, weights, q: float) -> float:
    """Quantile of values where each value counts by its weight."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    if len(values) == 1:
        return float(values[0])
    # Place each value at the middle of its share of the total weight.
    cum = np.cumsum(weights) - 0.5 * weights
    cum /= weights.sum()
    return float(np.interp(q, cum, values))


def select_analogues(df: pd.DataFrame, basis: EstimateBasis) -> pd.DataFrame:
    """Rows that match the facility type, chosen scopes and site types."""
    mask = (df["facility_type"] == basis.facility_type) & df["scope"].isin(basis.scopes)
    if basis.site_types:
        mask &= df["site_type"].isin(basis.site_types)
    if basis.exclude_ids:
        mask &= ~df["id"].isin(basis.exclude_ids)
    return df.loc[mask].copy()


def estimate(df: pd.DataFrame, basis: EstimateBasis) -> EstimateResult:
    """Run the estimate on an analogue table from ``load_analogues``."""
    if basis.capacity_mtpa <= 0:
        raise ValueError("Capacity must be above zero.")
    if not -1.0 < basis.class_low <= 0.0 <= basis.class_high:
        raise ValueError("Class range must be a negative low and a positive high.")

    sel = select_analogues(df, basis)
    if sel.empty:
        raise ValueError(
            "No analogues match. Widen the scope or site filters, or add your own projects."
        )

    n = basis.exponent()
    sel["escalation_factor"] = [
        escalation_factor(int(y), basis.estimate_year, basis.escalation_rate, basis.cost_index)
        for y in sel["cost_year"]
    ]
    sel["cost_escalated_usd_million"] = sel["cost_usd_million"] * sel["escalation_factor"]

    sel["analogue_location_factor"] = [
        basis.region_location_factors.get(r, 1.0) for r in sel["region"]
    ]
    sel["location_adjustment"] = basis.target_location_factor / sel["analogue_location_factor"]

    sel["size_ratio"] = basis.capacity_mtpa / sel["capacity_mtpa"]
    sel["size_factor"] = sel["size_ratio"] ** n
    sel["estimate_usd_million"] = (
        sel["cost_escalated_usd_million"] * sel["location_adjustment"] * sel["size_factor"]
    )
    sel["weight"] = [min(r, 1.0 / r) for r in sel["size_ratio"]]
    sel["weight_share"] = sel["weight"] / sel["weight"].sum()

    values, weights = sel["estimate_usd_million"], sel["weight"]
    p50 = weighted_quantile(values, weights, 0.5)
    a_p10 = weighted_quantile(values, weights, 0.1)
    a_p90 = weighted_quantile(values, weights, 0.9)
    p10 = min(a_p10, p50 * (1.0 + basis.class_low))
    p90 = max(a_p90, p50 * (1.0 + basis.class_high))

    warnings: list[str] = []
    if len(sel) < 3:
        warnings.append(
            f"Only {len(sel)} analogue(s) match. Treat the result with extra caution."
        )
    far = sel.loc[
        (sel["size_ratio"] > MAX_SAFE_SIZE_RATIO) | (sel["size_ratio"] < 1 / MAX_SAFE_SIZE_RATIO),
        "project",
    ]
    if len(far):
        warnings.append(
            "More than 3x size difference for: " + "; ".join(far)
            + ". Size scaling is less reliable there."
        )
    if (sel["scope"] != "plant_only").any():
        warnings.append(
            "Some analogues include more than the plant (for example a pipeline). "
            "Check the notes column."
        )
    oldest = int(sel["cost_year"].min())
    if basis.estimate_year - oldest > 10 and not basis.cost_index:
        warnings.append(
            f"Oldest analogue is from {oldest}. A constant escalation rate over "
            "more than 10 years is rough; consider a cost index."
        )

    sel = sel.sort_values("weight", ascending=False).reset_index(drop=True)
    return EstimateResult(
        basis=basis,
        analogues=sel,
        p10_usd_million=p10,
        p50_usd_million=p50,
        p90_usd_million=p90,
        analogue_p10_usd_million=a_p10,
        analogue_p90_usd_million=a_p90,
        warnings=warnings,
    )
