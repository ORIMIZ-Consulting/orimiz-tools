"""The estimating method: guideline Steps 2 to 12.

Each analog's unit cost (USD per tonne per annum, "USD/tpa") travels through
the steps one factor at a time. The journey table records the value after
every step, so a reviewer can check any number by hand.

    Step 4  escalate     u x f_esc               f_esc from rate, index or damped index
    Step 5  relocate     u x f_loc               f_loc = target factor / analog factor
    Step 6  scope        u x f_split x f_owner x f_site x f_multi x f_gas + co2
    Step 7  size         u x (T_target / T_analog) ^ (n - 1)  x  multi-train target factor
    Step 8  combine      weighted mean of the analogs
    Step 9  site items   decision tree with a materiality threshold
    Step 10 variants     choose the base among several methods
    Step 11 cost blocks  by cost type and by area
    Step 12 range        built from named uncertainties, checked against the class band

T is train size in MTPA. All money is in estimate-year US dollars.
Formulas, defaults and sources: docs/GUIDELINE.md and factors.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import factors as F
from .basis import EstimateBasis, Method, SiteItem, decision_log


# ================================================================ helpers
def weighted_quantile(values, weights, q: float) -> float:
    """Quantile of values where each value counts by its weight."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    if len(v) == 0:
        return float("nan")
    order = np.argsort(v)
    v, w = v[order], w[order]
    if len(v) == 1 or w.sum() == 0:
        return float(v[0])
    cum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, cum, v))


def _index_value(year: int, b: EstimateBasis, notes: list[str]) -> float:
    idx = b.cost_index
    if year in idx:
        return idx[year]
    nearest = min(idx, key=lambda y: abs(y - year))
    notes.append(
        f"Index has no value for {year}; extended from {nearest} at "
        f"{b.escalation_rate:.1%} a year."
    )
    return idx[nearest] * (1 + b.escalation_rate) ** (year - nearest)


def escalation_factor(from_year: int, to_year: int, how: str, b: EstimateBasis,
                      notes: list[str] | None = None) -> float:
    """Factor that moves a cost from one year's money to another's (Step 4).

    how: constant, constant_low, index, damped, or none.
    """
    notes = notes if notes is not None else []
    if how == "none":
        return 1.0
    if how == "constant":
        return (1 + b.escalation_rate) ** (to_year - from_year)
    if how == "constant_low":
        return (1 + b.escalation_rate_low) ** (to_year - from_year)
    if how in ("index", "damped"):
        if not b.cost_index:
            raise ValueError("This escalation method needs a cost index. Load one or choose a constant rate.")
        ratio = _index_value(to_year, b, notes) / _index_value(from_year, b, notes)
        if how == "index":
            return ratio
        return 1 + b.damping_f * (ratio - 1)
    raise ValueError(f"Unknown escalation method '{how}'")


def escalation_cases(b: EstimateBasis) -> tuple[list[tuple[str, str]], list[str]]:
    """The escalation cases to run, and any warning."""
    warn: list[str] = []
    mode = b.escalation_mode
    if mode == "auto":
        if b.cost_index:
            return [("High", "index"), ("Low", "damped")], warn
        warn.append(
            f"No cost index loaded, so escalation is a single case at "
            f"{b.escalation_rate:.1%} a year. This is rough over long periods; "
            f"load an index (for example {b.index_name}) to run two cases."
        )
        return [("Single", "constant")], warn
    if mode == "two_cases":
        return [("High", b.two_case_high), ("Low", b.two_case_low)], warn
    if mode in ("constant", "index", "damped"):
        return [("Single", mode)], warn
    raise ValueError(f"Unknown escalation mode '{mode}'")


def _gas_factor(level: str, b: EstimateBasis, notes: list[str], who: str) -> float:
    if b.gas_method == "off":
        return 1.0
    if level == "unknown":
        notes.append(f"{who}: gas richness unknown; treated as lean.")
        level = "lean"
    if b.gas_method == "simple":
        return b.gas_factors_simple["lean" if level == "lean" else "rich"]
    if level == "rich":
        notes.append(f"{who}: rich gas without a stated liquids scope; simple factor used.")
        return b.gas_factors_simple["rich"]
    return b.gas_factors_graded[level]


def _location_effect(factor: float, b: EstimateBasis) -> float:
    if b.location_method == "construction_share":
        return 1 + b.construction_share * (factor - 1)
    return factor


def target_train_factor(b: EstimateBasis) -> float:
    """Step 7 multi-train target: one-train unit cost to the target's train count."""
    if not (b.is_liquefaction and b.apply_multi_train) or b.trains <= 1:
        return 1.0
    if b.multi_train_method == "reverse_factor":
        return 1.0 / b.multi_train_factor
    if b.multi_train_method == "build_up":
        n = b.trains
        return (1 + (n - 1) * b.repeat_train_factor) / n
    return 1.0  # plant_capacity: handled in the size factor


# ================================================================ Step 2
def select_analogs(df: pd.DataFrame, b: EstimateBasis) -> pd.DataFrame:
    """All analogs of the facility type, with a status and reason for each."""
    pool = df[df["facility_type"] == b.facility_type].copy()
    small, large = F.SIZE_CLUSTERS
    t = b.train_size_mtpa
    target_cluster = "small" if t < small else "large" if t > large else "standard"
    reasons = []
    for _, r in pool.iterrows():
        why = ""
        has_split = pd.notna(r["plant_usd_million"])
        if r["id"] in b.exclude_ids:
            why = "Excluded by user"
        elif r["scope"] not in b.scopes and not (b.use_plant_splits and has_split):
            why = f"Scope '{r['scope']}' not accepted and no plant-only split"
        elif b.fid_window_years is not None and r["fid_year"] < b.estimate_year - b.fid_window_years:
            why = f"FID before {b.estimate_year - b.fid_window_years}"
        elif b.train_band is not None and not (
            b.train_band[0] <= r["train_size_mtpa"] / t <= b.train_band[1]
        ):
            why = f"Train size outside {b.train_band[0]:g} to {b.train_band[1]:g} times the target"
        elif b.site_types_allowed and r["site_type"] not in b.site_types_allowed:
            why = "Site type not accepted"
        elif (b.is_liquefaction and b.cluster_rule and target_cluster != "standard"
              and r["cluster"] != target_cluster):
            why = f"Not in the {target_cluster}-train cluster"
        elif (b.process_family_filter and b.process_family not in ("not_chosen",)
              and r["process_family"] != b.process_family):
            why = "Different process family"
        reasons.append(why)
    pool["selection_note"] = reasons
    pool["selected"] = pool["selection_note"] == ""
    return pool.reset_index(drop=True)


# ================================================================ Steps 4 to 7
def normalize(sel: pd.DataFrame, b: EstimateBasis, how: str, exponent: float,
              notes: list[str]) -> pd.DataFrame:
    """Each analog's unit cost after every step, for one escalation case."""
    liq = b.is_liquefaction
    target_loc = b.target_location_factor()
    target_site = b.site_factors.get(b.site_type, 1.0) if (liq and b.apply_site_factor) else 1.0
    target_gas = _gas_factor(b.feed_gas, b, notes, "Target") if liq else 1.0
    plant_scaling = liq and b.multi_train_method == "plant_capacity"
    f_target = target_train_factor(b)
    rows = []
    for _, r in sel.iterrows():
        rec = {"id": r["id"], "project": r["project"], "case": how}
        u = r["unit_cost_reported"]
        rec["u_reported"] = u

        # Step 4: escalation
        f_esc = escalation_factor(int(r["cost_year"]), b.estimate_year, how, b, notes)
        rec["f_esc"] = f_esc
        u *= f_esc
        rec["u_escalated"] = u

        # Step 5: location
        if r["id"] in b.analog_location_overrides:
            loc_a = b.analog_location_overrides[r["id"]]
        else:
            loc_a = b.location_groups.get(r["location_group"], 1.0) + F.LOCATION_STEP * r["location_steps"]
        rec["loc_analog"] = loc_a
        rec["loc_target"] = target_loc
        f_loc = _location_effect(target_loc, b) / _location_effect(loc_a, b)
        rec["f_loc"] = f_loc
        u *= f_loc
        rec["u_located"] = u

        # Step 6: scope and complexity
        f_split = 1.0
        if r["scope"] != "plant_only" and b.use_plant_splits and pd.notna(r["plant_usd_million"]):
            keep_pipeline = r["scope"] == "plant_plus_pipeline" and "pipeline" in b.battery_limits
            if not keep_pipeline:
                f_split = r["plant_usd_million"] / r["cost_usd_million"]
        f_owner = 1.0
        if b.apply_owner_costs:
            if r["cost_basis"] == "epc" and "owners_costs" in b.battery_limits:
                f_owner = b.owner_cost_factor
            elif r["cost_basis"] != "epc" and "owners_costs" not in b.battery_limits:
                f_owner = 1.0 / b.owner_cost_factor
        f_site = 1.0
        if liq and b.apply_site_factor:
            f_site = b.site_factors.get(r["site_type"], 1.0) / target_site
        f_multi = 1.0
        if liq and b.apply_multi_train and r["trains"] > 1 and not plant_scaling:
            f_multi = b.multi_train_factor
        f_gas = 1.0
        if liq and b.gas_method != "off":
            analog_gas = _gas_factor(r["liquids_scope"], b, notes, r["id"]) if r["gas_adjust"] else 1.0
            f_gas = target_gas / analog_gas
        co2 = 0.0
        if liq and b.apply_co2_removal and r["co2_sequestration"]:
            co2 = -b.co2_adder[1]
        f_hybrid = (1 - b.hybrid_step_share) if b.adjustment_method == "hybrid" else 1.0
        rec.update(f_split=f_split, f_owner=f_owner, f_site=f_site, f_multi=f_multi,
                   f_gas=f_gas, co2_adj=co2, f_hybrid=f_hybrid)
        u = (u * f_split * f_owner * f_site * f_multi * f_gas + co2) * f_hybrid
        rec["n_adjustments"] = int(sum([
            not math.isclose(f_split, 1), not math.isclose(f_owner, 1), not math.isclose(f_site, 1),
            not math.isclose(f_multi, 1), not math.isclose(f_gas, 1), co2 != 0,
        ]))
        rec["u_scoped"] = u

        # Step 7: size
        if plant_scaling:
            ratio = b.capacity_mtpa / r["capacity_mtpa"]
        else:
            ratio = b.train_size_mtpa / r["train_size_mtpa"]
        rec["size_ratio"] = ratio
        rec["f_size"] = ratio ** (exponent - 1)
        rec["f_target_trains"] = f_target
        u *= rec["f_size"] * f_target
        rec["u_final"] = u
        rows.append(rec)
    return pd.DataFrame(rows)


def fit_exponent(journey: pd.DataFrame, sel: pd.DataFrame) -> dict:
    """Fit n from the analogs (shown only; Step 7 says not to rely on it)."""
    j = journey.merge(sel[["id", "train_size_mtpa"]], on="id")
    j = j[j["u_scoped"] > 0]
    if len(j) < 3:
        return {"n": float("nan"), "r2": float("nan"), "count": len(j)}
    x = np.log(j["train_size_mtpa"].to_numpy())
    y = np.log(j["u_scoped"].to_numpy())
    if np.ptp(x) == 0:
        return {"n": float("nan"), "r2": float("nan"), "count": len(j)}
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"n": float(slope + 1), "r2": r2, "count": len(j)}


def calibrate_damping(df: pd.DataFrame, b: EstimateBasis) -> pd.DataFrame:
    """Step 4 calibration: how much of the index change real costs followed.

    A clean pair has the same region, site type and contractor, both figures
    are budgets, and the FIDs are at least five years apart.
        f = (actual cost ratio - 1) / (index ratio - 1)
    Actual costs are compared after location, scope and size normalization,
    without escalation.
    """
    cols = ["earlier", "later", "years", "actual_ratio", "index_ratio", "f"]
    if not b.cost_index:
        return pd.DataFrame(columns=cols)
    pool = df[(df["facility_type"] == b.facility_type) & (df["contingency_status"] == "budget")]
    pool = pool[pool["scope"].isin(b.scopes) | pool["plant_usd_million"].notna()]
    pool = pool[~pool["epc_contractor"].str.lower().isin(["", "not stated"])]
    if len(pool) < 2:
        return pd.DataFrame(columns=cols)
    notes: list[str] = []
    norm = normalize(pool, b, "none", b.resolved_exponent(), notes).set_index("id")
    rows = []
    recs = pool.to_dict("records")
    for i, a in enumerate(recs):
        for c in recs[i + 1:]:
            early, late = (a, c) if a["fid_year"] <= c["fid_year"] else (c, a)
            if (late["fid_year"] - early["fid_year"] < 5 or a["region"] != c["region"]
                    or a["site_type"] != c["site_type"] or a["epc_contractor"] != c["epc_contractor"]):
                continue
            actual = norm.loc[late["id"], "u_final"] / norm.loc[early["id"], "u_final"]
            idx = (_index_value(int(late["cost_year"]), b, notes)
                   / _index_value(int(early["cost_year"]), b, notes))
            f = (actual - 1) / (idx - 1) if not math.isclose(idx, 1) else float("nan")
            rows.append({
                "earlier": f"{early['project']} ({early['cost_year']})",
                "later": f"{late['project']} ({late['cost_year']})",
                "years": int(late["cost_year"] - early["cost_year"]),
                "actual_ratio": actual, "index_ratio": idx, "f": f,
            })
    return pd.DataFrame(rows, columns=cols)


# ================================================================ Step 8
def rubric(sel: pd.DataFrame, first_case: pd.DataFrame, b: EstimateBasis) -> pd.DataFrame:
    j = first_case.set_index("id")
    out = []
    for _, r in sel.iterrows():
        ratio = r["train_size_mtpa"] / b.train_size_mtpa
        pts = {
            "same_region": bool(b.target_region) and r["region"] == b.target_region,
            "clean_figure": r["scope"] == "plant_only" and math.isclose(j.loc[r["id"], "f_split"], 1)
            and r["cost_basis"] in ("budget", "outturn", "epc"),
            "size_close": max(ratio, 1 / ratio) <= 1.5,
            "few_adjustments": j.loc[r["id"], "n_adjustments"] <= 2,
            "recent": b.estimate_year - r["fid_year"] <= 10,
        }
        rec = {"id": r["id"], **pts}
        rec["rubric_points"] = int(sum(pts.values()))
        rec["suggested_weight"] = F.rubric_weight(rec["rubric_points"])
        out.append(rec)
    return pd.DataFrame(out)


def choose_weights(rub: pd.DataFrame, sel: pd.DataFrame, b: EstimateBasis,
                   warnings: list[str]) -> pd.DataFrame:
    w = rub.merge(sel[["id", "project", "train_size_mtpa", "capacity_mtpa"]], on="id")
    if b.weighting == "equal":
        w["weight"] = 1.0
    elif b.weighting == "size":
        if b.multi_train_method == "plant_capacity" and b.is_liquefaction:
            ratio = w["capacity_mtpa"] / b.capacity_mtpa
        else:
            ratio = w["train_size_mtpa"] / b.train_size_mtpa
        w["weight"] = np.minimum(ratio, 1 / ratio)
    elif b.weighting == "rubric":
        w["weight"] = w["suggested_weight"].astype(float)
    elif b.weighting == "judgment":
        w["weight"] = [float(b.weights.get(i, s)) for i, s in zip(w["id"], w["suggested_weight"])]
        missing = [
            i for i, s in zip(w["id"], w["suggested_weight"])
            if i in b.weights and b.weights[i] != s and not b.weight_reasons.get(i)
        ]
        if missing:
            warnings.append(
                "A reason is required where your weight differs from the rubric: " + ", ".join(missing)
            )
    else:
        raise ValueError(f"Unknown weighting '{b.weighting}'")
    w["reason"] = [b.weight_reasons.get(i, "") for i in w["id"]]
    w["dropped"] = w["id"].isin(list(b.drop_reasons))
    w["drop_reason"] = [b.drop_reasons.get(i, "") for i in w["id"]]
    w.loc[w["dropped"], "weight"] = 0.0
    return w


# ================================================================ Step 9
def site_register(items: list[SiteItem], base: float, b: EstimateBasis) -> pd.DataFrame:
    """Apply the decision tree to each site item."""
    rows = []
    for it in items:
        hybrid_block = b.adjustment_method == "hybrid" and it.category in ("storage", "marine")
        if hybrid_block:
            removed = ("tanks" not in b.battery_limits and it.category == "storage") or (
                "marine" not in b.battery_limits and it.category == "marine")
            treatment = "Outside battery limits" if removed else "Hybrid block, added to base"
            adder = 0.0 if removed else it.central
            d_low, d_high = (0.0, 0.0) if removed else (it.low - it.central, it.high - it.central)
        elif it.analogs_carry_typical:
            treatment = "Analogs carry it: difference carried as risk or opportunity"
            adder, d_low, d_high = 0.0, it.low, it.high
        elif abs(it.central) >= b.materiality * base:
            treatment = "Missing from analogs and material: added to base"
            adder, d_low, d_high = it.central, it.low - it.central, it.high - it.central
        else:
            treatment = "Missing from analogs but below materiality: noted only"
            adder, d_low, d_high = 0.0, 0.0, 0.0
        rows.append({
            "item": it.name, "category": it.category, "driver": it.driver,
            "analogs_carry_typical": it.analogs_carry_typical,
            "central": it.central, "low": it.low, "high": it.high,
            "treatment": treatment, "base_adder": adder,
            "opportunity": min(0.0, d_low), "risk": max(0.0, d_high),
            "status": it.status, "source": it.source,
        })
    cols = ["item", "category", "driver", "analogs_carry_typical", "central", "low", "high",
            "treatment", "base_adder", "opportunity", "risk", "status", "source"]
    return pd.DataFrame(rows, columns=cols)


def tank_cost(volume_m3: float, count: int = 1, ref: dict | None = None) -> float:
    """Full-containment tank cost, USD million in the reference year (Step 9 library)."""
    ref = ref or F.TANK_REFERENCE
    return count * ref["cost_musd"] * (volume_m3 / ref["volume_m3"]) ** ref["exponent"]


def dredging_cost(volume_m3: float) -> tuple[float, float]:
    """Low and high dredging cost, USD million."""
    lo, hi = F.DREDGING_USD_PER_M3
    return volume_m3 * lo / 1e6, volume_m3 * hi / 1e6


def co2_item(capacity_mtpa: float, b: EstimateBasis | None = None) -> SiteItem:
    lo, mid, hi = (b.co2_adder if b else F.CO2_ADDER_USD_PER_TPA)
    return SiteItem(
        name="CO2 removal and sequestration", category="co2", analogs_carry_typical=False,
        central=mid * capacity_mtpa, low=lo * capacity_mtpa, high=hi * capacity_mtpa,
        driver=f"USD {lo:g} to {hi:g} per tpa on {capacity_mtpa:g} MTPA", source=F.OIES,
    )


# ================================================================ Step 11
def area_blocks(plant_base: float, b: EstimateBasis) -> dict[str, float]:
    """Split a full-scope plant cost into area blocks (before site items)."""
    owner_share = F.COST_TYPE_SHARES["Owner's costs"] if "owners_costs" in b.battery_limits else 0.0
    epc = plant_base * (1 - owner_share)
    if b.adjustment_method == "hybrid":
        epc_full = epc / (1 - b.hybrid_step_share)
        process = F.PROCESS_SHARE_OF_EPC * epc_full
        sm = 0.0  # comes from the hybrid site items
    else:
        process = F.PROCESS_SHARE_OF_EPC * epc
        sm = F.STORAGE_MARINE_SHARE_OF_EPC * epc
    rest = epc - process - sm
    return {
        "Process train": process,
        "Storage and marine": sm,
        "Utilities and offsites": F.UTILITIES_SHARE_OF_REMAINDER * rest,
        "Site works and infrastructure": (1 - F.UTILITIES_SHARE_OF_REMAINDER) * rest,
        "Owner's costs": plant_base * owner_share,
    }


def battery_limit_removal(blocks: dict[str, float], b: EstimateBasis) -> dict[str, float]:
    """Blocks removed because they are outside the battery limits."""
    bl = b.battery_limits
    out = {}
    if "trains" not in bl:
        out["Process train"] = blocks["Process train"]
    if "utilities" not in bl:
        out["Utilities and offsites"] = blocks["Utilities and offsites"]
    if "site_works" not in bl:
        out["Site works and infrastructure"] = blocks["Site works and infrastructure"]
    sm_share = (0.5 if "tanks" not in bl else 0.0) + (0.5 if "marine" not in bl else 0.0)
    if sm_share and blocks["Storage and marine"]:
        out["Storage and marine"] = sm_share * blocks["Storage and marine"]  # 50/50 split: judgment
    return out


# ================================================================ core run
@dataclass
class _Core:
    pool: pd.DataFrame
    sel: pd.DataFrame
    journey: pd.DataFrame
    weights: pd.DataFrame
    cases: pd.DataFrame
    exponent: float
    fitted: dict
    register: pd.DataFrame
    blocks: dict[str, float]
    removed: dict[str, float]
    contingency: dict
    stats: dict
    notes: list[str]
    warnings: list[str]

    @property
    def central(self) -> float:
        return float(self.cases["base"].mean())


def _core(df: pd.DataFrame, b: EstimateBasis) -> _Core:
    warnings: list[str] = []
    notes: list[str] = []
    if b.train_size_mtpa <= 0 or b.trains < 1:
        raise ValueError("Train size must be above zero and trains at least one.")
    if not -1.0 < b.class_low <= 0.0 <= b.class_high:
        raise ValueError("Accuracy target must be a negative low and a positive high.")

    pool = select_analogs(df, b)
    sel = pool[pool["selected"]].reset_index(drop=True)
    if sel.empty:
        raise ValueError("No analogs pass the filters. Loosen a filter in Step 2 or add your own analogs.")

    cases, w_esc = escalation_cases(b)
    warnings += w_esc
    n = b.resolved_exponent()

    first = normalize(sel, b, cases[0][1], n, notes)
    fitted = fit_exponent(first, sel)
    if b.use_fitted_exponent:
        if math.isnan(fitted["n"]):
            warnings.append("Fitted exponent not available; default used.")
        else:
            n = fitted["n"]
            warnings.append(
                f"Using the fitted exponent n = {n:.2f} (R2 = {fitted['r2']:.2f}). "
                "The guideline advises taking n from practice."
            )
            first = normalize(sel, b, cases[0][1], n, notes)
    journeys = [first.assign(case=cases[0][0])]
    for name, how in cases[1:]:
        journeys.append(normalize(sel, b, how, n, notes).assign(case=name))
    journey = pd.concat(journeys, ignore_index=True)

    # Step 8
    rub = rubric(sel, first, b)
    wt = choose_weights(rub, sel, b, warnings)
    mean_val = journey.groupby("id")["u_final"].mean()
    wt["value"] = wt["id"].map(mean_val)
    kept = wt[~wt["dropped"] & (wt["weight"] > 0)]
    if len(kept) < b.min_count_stop:
        raise ValueError(
            f"Only {len(kept)} analog(s) remain; the minimum is {b.min_count_stop}. "
            "Loosen a filter or add analogs."
        )
    if len(kept) < b.min_count_warn:
        warnings.append(f"Only {len(kept)} analogs remain (fewer than {b.min_count_warn}): low confidence.")
    median = float(kept["value"].median())
    wt["vs_median"] = wt["value"] / median - 1
    wt["outlier"] = wt["vs_median"].abs() > b.outlier_threshold
    flagged = wt[wt["outlier"] & ~wt["dropped"]]
    if len(flagged):
        warnings.append(
            f"Outliers (more than {b.outlier_threshold:.0%} from the median): "
            + ", ".join(flagged["project"]) + ". Keep or drop each, with a reason."
        )
    ww = kept["weight"] / kept["weight"].sum()
    stats = {
        "weighted_mean": float((kept["value"] * ww).sum()),
        "simple_mean": float(kept["value"].mean()),
        "median": median,
        "count": int(len(kept)),
    }
    gap = max(abs(stats["simple_mean"] / stats["weighted_mean"] - 1),
              abs(stats["median"] / stats["weighted_mean"] - 1))
    if gap > F.STATS_GAP_WARNING:
        warnings.append(
            f"Weighted mean, simple mean and median differ by up to {gap:.0%}: "
            "the weights are doing a lot of work and deserve a second look."
        )
    wt["weight_share"] = np.where(wt["dropped"], 0.0, wt["weight"] / kept["weight"].sum())

    # Central per escalation case, then Steps 9, 11 and contingency
    budget_share = float(
        wt.merge(sel[["id", "contingency_status"]], on="id")
        .query("contingency_status == 'budget'")["weight_share"].sum()
    )
    case_rows = []
    weight_map = dict(zip(kept["id"], kept["weight"]))
    for name, how in cases:
        jc = journey[journey["case"] == name]
        jc = jc[jc["id"].isin(weight_map)]
        w = jc["id"].map(weight_map)
        unit = float((jc["u_final"] * w).sum() / w.sum())
        p10 = weighted_quantile(jc["u_final"], w, 0.1)
        p90 = weighted_quantile(jc["u_final"], w, 0.9)
        case_rows.append({"case": name, "method": how, "unit": unit,
                          "spread_low": p10 / unit - 1, "spread_high": p90 / unit - 1,
                          "plant_base": unit * b.capacity_mtpa})
    cases_df = pd.DataFrame(case_rows)
    plant_central = float(cases_df["plant_base"].mean())
    blocks = area_blocks(plant_central, b)
    removed = battery_limit_removal(blocks, b)
    removed_share = sum(removed.values()) / plant_central if plant_central else 0.0
    pre_items = plant_central * (1 - removed_share)

    items = list(b.site_items)
    if b.is_liquefaction and b.co2_sequestration and not any(i.category == "co2" for i in items):
        items.append(co2_item(b.capacity_mtpa, b))
    register = site_register(items, pre_items, b)
    adders = float(register["base_adder"].sum())

    contingency = {"budget_weight_share": budget_share, "rate": b.contingency_rate,
                   "applies": budget_share < 0.5, "line_share": 0.0}
    if contingency["applies"]:
        contingency["line_share"] = b.contingency_rate * (1 - budget_share)
        warnings.append(
            f"Only {budget_share:.0%} of the weight sits on sanctioned budgets, so a contingency "
            f"line of {contingency['line_share']:.1%} is added for the missing share."
        )
    cases_df["removed"] = cases_df["plant_base"] * removed_share
    cases_df["site_adders"] = adders
    pre_cont = cases_df["plant_base"] - cases_df["removed"] + adders
    cases_df["contingency"] = pre_cont * contingency["line_share"]
    cases_df["base"] = pre_cont + cases_df["contingency"]

    return _Core(pool, sel, journey, wt, cases_df, n, fitted, register, blocks, removed,
                 contingency, stats, sorted(set(notes)), warnings)


# ================================================================ Step 10
def choose_base(methods: list[Method], rule: str = "combined") -> tuple[Method, str]:
    """Pick the base method. Returns the method and a sentence on why."""
    if len(methods) == 1:
        return methods[0], "Only one method."
    values = sorted(m.value for m in methods)
    lo, hi = values[0], values[-1]
    mid = float(np.median(values))
    if rule == "fewest":
        m = min(methods, key=lambda m: (m.judgment_calls, abs(m.value - mid)))
        return m, "Fewest judgment calls."
    if rule == "middle":
        m = min(methods, key=lambda m: abs(m.value - mid))
        return m, "Nearest the middle of the spread."
    if rule == "conservative":
        m = max(methods, key=lambda m: m.value)
        return m, "Highest result (most conservative)."
    fewest = min(m.judgment_calls for m in methods)
    cands = [m for m in methods if m.judgment_calls == fewest]
    inner = [m for m in cands if not (math.isclose(m.value, lo) or math.isclose(m.value, hi))]
    if inner:
        m = min(inner, key=lambda m: abs(m.value - mid))
        return m, "Fewest judgment calls and not at either end."
    m = min(cands, key=lambda m: abs(m.value - mid))
    return m, "Fewest judgment calls; all such methods sit at an end, so the one nearest the middle."


def brownfield_block_method(df: pd.DataFrame, b: EstimateBasis, adders: float) -> Method:
    """Price a brownfield option block by block from the greenfield estimate."""
    s = b.brownfield_shares
    gf = _core(df, b.with_changes(site_type="greenfield", brownfield_shares=None, methods=[],
                                  site_items=[], co2_sequestration=False))
    blocks = area_blocks(float(gf.cases["plant_base"].mean()), b)
    epc = (blocks["Process train"] + s.utilities * blocks["Utilities and offsites"]
           + s.site_works * blocks["Site works and infrastructure"]
           + s.storage_marine * blocks["Storage and marine"] + s.tie_ins_musd)
    owner_share = F.COST_TYPE_SHARES["Owner's costs"] if "owners_costs" in b.battery_limits else 0.0
    value = epc / (1 - owner_share) + adders
    note = (f"Process train 100%; utilities {s.utilities:.0%}, site works {s.site_works:.0%}, "
            f"storage and marine {s.storage_marine:.0%} of the greenfield blocks; tie-ins "
            f"USD {s.tie_ins_musd:,.0f}m.")
    return Method("Block by block", value, judgment_calls=4, note=note)


# ================================================================ result
@dataclass
class EstimateResult:
    basis: EstimateBasis
    pool: pd.DataFrame
    journey: pd.DataFrame
    weights: pd.DataFrame
    stats: dict
    cases: pd.DataFrame
    exponent: float
    fitted_exponent: dict
    calibration: pd.DataFrame
    site_register: pd.DataFrame
    methods: pd.DataFrame
    base_method: str
    base_reason: str
    central: float
    low: float
    high: float
    range_parts: dict
    blocks_by_area: pd.DataFrame
    blocks_by_type: pd.DataFrame
    sensitivities: pd.DataFrame
    contingency: dict
    log: pd.DataFrame
    references: pd.DataFrame
    warnings: list[str]
    notes: list[str] = field(default_factory=list)

    @property
    def unit_cost(self) -> float:
        return self.central / self.basis.capacity_mtpa

    def in_report_currency(self, value: float) -> float:
        return value * self.basis.report_fx

    def summary(self) -> str:
        b = self.basis
        cur = b.report_currency
        lines = [
            f"FEL 1 estimate, {b.option_name}: {b.trains} x {b.train_size_mtpa:g} MTPA "
            f"{F.FACILITY_TYPES[b.facility_type]}, {b.site_type}, {b.location_name}",
            f"Money of {b.estimate_year}, {cur} million",
            f"  Low   {self.in_report_currency(self.low):>10,.0f}",
            f"  Base  {self.in_report_currency(self.central):>10,.0f}   "
            f"({self.unit_cost:,.0f} USD per tpa)",
            f"  High  {self.in_report_currency(self.high):>10,.0f}",
            f"  {self.stats['count']} analogs, n = {self.exponent:.2f}, base method: {self.base_method}",
            "  AACE Class 5. Reasoned bounds, not a statistical P10 and P90.",
        ]
        lines += [f"  Note: {w}" for w in self.warnings]
        return "\n".join(lines)


def estimate(df: pd.DataFrame, b: EstimateBasis) -> EstimateResult:
    """Run the full method on a table from ``load_analogs``."""
    core = _core(df, b)
    warnings = list(core.warnings)
    if not b.is_liquefaction:
        warnings.insert(0, "Preview: the guideline does not yet cover this facility type "
                           "(Section 18). Liquefaction-only factors are switched off.")
    sel = core.sel

    # Warnings that look at inputs and the analog set
    small, large = F.SIZE_CLUSTERS
    if b.is_liquefaction and not small <= b.train_size_mtpa <= large:
        warnings.append(
            f"Target train of {b.train_size_mtpa:g} MTPA is outside 1 to 6 MTPA: the analog pool "
            "changes there. Use a separate cluster rather than stretching the exponent."
        )
    used = sel[sel["id"].isin(core.weights.loc[core.weights["weight"] > 0, "id"])]
    tmax, tmin = used["train_size_mtpa"].max(), used["train_size_mtpa"].min()
    if b.train_size_mtpa > b.extrapolation_limit * tmax or b.train_size_mtpa < tmin / b.extrapolation_limit:
        warnings.append(
            f"Target train is more than {b.extrapolation_limit:g} times beyond the analog range "
            f"({tmin:.2g} to {tmax:.2g} MTPA): size scaling is an extrapolation."
        )
    if b.is_liquefaction and b.multi_train_method == "plant_capacity":
        warnings.append("Scaling on plant capacity overstates the economy of scale; keep it for comparison.")
    for item in ("upstream", "pipeline"):
        if item in b.battery_limits:
            warnings.append(f"{item.capitalize()} is inside your battery limits but outside the analogs' "
                            "scope. Add it as a site item.")
    if b.adjustment_method == "multiply":
        big = core.register[core.register["category"].isin(["storage", "marine"])]
        span = (big[["central", "low", "high"]].abs().max(axis=1) > b.materiality * core.central).any()
        if span:
            warnings.append("Storage or marine items differ from typical by more than the materiality "
                            "threshold. Consider the hybrid method (Step 3, option C).")
    elif not (core.register["category"].isin(["storage", "marine"])).any():
        warnings.append("Hybrid method chosen but no storage or marine blocks given in Step 9.")
    if b.process_family not in ("not_chosen",):
        diff = used[used["process_family"] != b.process_family]
        if len(diff):
            warnings.append(f"{len(diff)} analogs use a different process family; carried as a "
                            f"+/-{F.TECHNOLOGY_SENSITIVITY:.0%} sensitivity, not a factor.")

    # Step 10: methods
    analog_central = core.central
    methods = [Method("Analog factor method", analog_central, b.analog_method_judgment_calls,
                      "Normalized analogs, Steps 2 to 9")]
    if b.brownfield_shares is not None and b.is_liquefaction and b.site_type != "greenfield":
        methods.append(brownfield_block_method(df, b, float(core.register["base_adder"].sum())))
    methods += list(b.methods)
    chosen, why = choose_base(methods, b.base_rule)
    central = chosen.value
    if len(methods) == 1 and b.purpose != "screen":
        warnings.append("The guideline asks for at least two independent methods. Add one in Step 10.")
    if len(methods) > 1 and not b.method_gap_note:
        warnings.append("Explain the gap between the methods in writing (Step 10).")

    # Step 12: range
    low_case = float(core.cases["base"].min())
    high_case = float(core.cases["base"].max())
    s_low = float(core.cases["spread_low"].mean())
    s_high = float(core.cases["spread_high"].mean())
    g_low, g_high = b.definition_growth
    opp = float(core.register["opportunity"].sum())
    risk = float(core.register["risk"].sum())
    shift = central - analog_central  # a chosen variant method moves the range with it
    built_low = (low_case + shift) * (1 + s_low + g_low) + opp
    built_high = (high_case + shift) * (1 + s_high + g_high) + risk
    band_low = central * (1 + b.class_low)
    band_high = central * (1 + b.class_high)
    if b.range_method == "class_band":
        low, high = band_low, band_high
    elif b.range_method == "analog_spread":
        low, high = central * (1 + s_low), central * (1 + s_high)
    else:
        low, high = built_low, built_high
    mvals = [m.value for m in methods]
    low, high = min(low, min(mvals)), max(high, max(mvals))
    narrower = low > band_low or high < band_high
    if b.range_method != "class_band" and narrower:
        if b.widen_to_class_band:
            low, high = min(low, band_low), max(high, band_high)
            warnings.append("Range widened to the Class 5 band.")
        else:
            warnings.append(
                f"The range ({low / central - 1:+.0%} / {high / central - 1:+.0%}) is narrower than the "
                f"class band ({b.class_low:+.0%} / {b.class_high:+.0%}). Widen it, or record why this "
                "project is better defined than a typical Class 5."
            )
    range_parts = {
        "low_case": low_case, "high_case": high_case, "analog_spread_low": s_low,
        "analog_spread_high": s_high, "definition_growth_low": g_low,
        "definition_growth_high": g_high, "site_opportunities": opp, "site_risks": risk,
        "class_band_low": band_low, "class_band_high": band_high,
        "built_low": built_low, "built_high": built_high, "method": b.range_method,
    }

    # Step 11: blocks for the final base
    # Blocks sum to the analog central; a chosen variant method rescales them.
    scale = central / analog_central if analog_central else 1.0
    area = []
    for name, value in core.blocks.items():
        removed = core.removed.get(name, 0.0)
        note = ""
        if removed:
            note = "Outside battery limits" if math.isclose(removed, value) else "Partly outside battery limits"
        area.append({"block": name, "usd_million": value - removed, "note": note})
    area_df = pd.DataFrame(area)
    extra = [
        {"block": "Site-specific additions", "usd_million": float(core.register["base_adder"].sum()), "note": "Step 9"},
        {"block": "Contingency line", "usd_million": float(core.cases["contingency"].mean()), "note": "Step 12"},
    ]
    area_df = pd.concat([area_df, pd.DataFrame(extra)], ignore_index=True)
    if not math.isclose(scale, 1.0):
        area_df["usd_million"] *= scale
        area_df["note"] = area_df["note"].where(area_df["note"] != "", f"Scaled to {chosen.name}")
    area_df["share"] = area_df["usd_million"] / area_df["usd_million"].sum()
    type_df = pd.DataFrame([
        {"cost_type": k, "share": v, "usd_million": v * central} for k, v in F.COST_TYPE_SHARES.items()
    ])

    # Sensitivities
    sens = [{"sensitivity": "Base", "central": central}]
    for n_alt in F.EXPONENT_SENSITIVITY:
        try:
            alt = _core(df, b.with_changes(exponent=n_alt, use_fitted_exponent=False)).central
            sens.append({"sensitivity": f"Exponent n = {n_alt}", "central": alt + shift})
        except ValueError:
            pass
    for step in (-1, 1):
        if b.location_factor is not None:
            ch = {"location_factor": b.location_factor + step * F.LOCATION_STEP}
        else:
            ch = {"location_steps": b.location_steps + step}
        try:
            alt = _core(df, b.with_changes(**ch)).central
            sens.append({"sensitivity": f"Target location {step:+d} step ({step * F.LOCATION_STEP:+.2f})",
                         "central": alt + shift})
        except ValueError:
            pass
    t = F.TECHNOLOGY_SENSITIVITY
    sens += [{"sensitivity": f"Technology -{t:.0%}", "central": central * (1 - t)},
             {"sensitivity": f"Technology +{t:.0%}", "central": central * (1 + t)}]
    for _, c in core.cases.iterrows():
        if len(core.cases) > 1:
            sens.append({"sensitivity": f"Escalation case: {c['case']} ({c['method']})", "central": c["base"] + shift})
    if b.is_liquefaction and b.trains > 1 and b.multi_train_method != "plant_capacity":
        try:
            alt = _core(df, b.with_changes(multi_train_method="plant_capacity")).central
            sens.append({"sensitivity": "Scale on plant capacity (comparison only)", "central": alt + shift})
        except ValueError:
            pass
    sens_df = pd.DataFrame(sens)
    sens_df["change"] = sens_df["central"] / central - 1

    calib = calibrate_damping(df, b)

    # Decision log and references
    log = pd.DataFrame(decision_log(b))
    if b.purpose == "gate1":
        unreviewed = int((log["reason"] == "Default accepted").sum())
        if unreviewed:
            warnings.append(f"Gate 1: {unreviewed} switches are at their default with no recorded "
                            "review. Add a reason for each step.")
    changed_no_reason = log[(log["changed"] == True) & (log["reason"] == "")]  # noqa: E712
    if len(changed_no_reason):
        warnings.append(f"{len(changed_no_reason)} changed switches have no reason in the decision log.")
    refs = [{"item": r["project"], "used_for": "Analog", "source": r["source_url"]}
            for _, r in used.iterrows()]
    refs += [{"item": a, "used_for": "Factor: " + s, "source": u} for a, s, u in F.FACTOR_REFERENCES]
    refs_df = pd.DataFrame(refs)

    methods_df = pd.DataFrame([vars(m) for m in methods])
    methods_df["chosen"] = methods_df["name"] == chosen.name

    return EstimateResult(
        basis=b, pool=core.pool, journey=core.journey, weights=core.weights, stats=core.stats,
        cases=core.cases, exponent=core.exponent, fitted_exponent=core.fitted, calibration=calib,
        site_register=core.register, methods=methods_df, base_method=chosen.name, base_reason=why,
        central=central, low=low, high=high, range_parts=range_parts, blocks_by_area=area_df,
        blocks_by_type=type_df, sensitivities=sens_df, contingency=core.contingency, log=log,
        references=refs_df, warnings=warnings, notes=core.notes,
    )


# ================================================================ Step 12: comparing options
def compare_options(a: EstimateResult, b: EstimateResult) -> dict:
    """Range the difference B - A with shared drivers held together.

    Escalation case, analog spread and definition growth move both options
    together. Site items that appear in only one option do not.
    """
    pa, pb = a.range_parts, b.range_parts
    shift_a = a.central - (pa["low_case"] + pa["high_case"]) / 2
    shift_b = b.central - (pb["low_case"] + pb["high_case"]) / 2
    diffs = []
    for case_a, case_b in ((pa["low_case"], pb["low_case"]), (pa["high_case"], pb["high_case"])):
        d = (case_b + shift_b) - (case_a + shift_a)
        for spread, growth in ((pa["analog_spread_low"], pa["definition_growth_low"]),
                               (pa["analog_spread_high"], pa["definition_growth_high"])):
            diffs.append(d * (1 + spread + growth))

    def unique(r1, r2):
        """Site items in r1 that r2 does not share (same name and values)."""
        keys2 = {(x.item, x.central, x.low, x.high) for x in r2.site_register.itertuples()}
        mask = pd.Series(
            [(x.item, x.central, x.low, x.high) not in keys2 for x in r1.site_register.itertuples()],
            index=r1.site_register.index, dtype=bool,
        )
        return r1.site_register.loc[mask]

    ua, ub = unique(a, b), unique(b, a)
    low = min(diffs) + ub["opportunity"].sum() - ua["risk"].sum()
    high = max(diffs) + ub["risk"].sum() - ua["opportunity"].sum()
    overlap = not (a.high < b.low or b.high < a.low)
    return {
        "option_a": a.basis.option_name, "option_b": b.basis.option_name,
        "central_difference": b.central - a.central, "low": float(low), "high": float(high),
        "independent_ranges_overlap": overlap,
        "note": ("Two overlapping ranges do not mean the difference might be zero; "
                 "read the correlated difference instead.") if overlap else "",
    }
