"""The basis of estimate: key inputs (Step 1) and every method switch.

Guideline principle 1: every method choice is a switch with options, a
default and a source. Principle 2: every switch is logged, defaults included.
``EstimateBasis`` holds them all; ``SWITCHES`` describes them for the log.

The defaults are for onshore liquefaction. Use ``make_basis()`` for the
preview facility types (FLNG, regas, FSRU): it switches off the filters and
factors that only apply to liquefaction.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from datetime import date

from . import factors as F


@dataclass
class SiteItem:
    """A site-specific item (Step 9). Money in USD million, estimate-year money.

    analogs_carry_typical: the analogs already include this item in a typical
    form. Then ``central`` should be 0 and low/high are the target's difference
    from typical. Otherwise central, low and high are the item's own cost.
    """

    name: str
    category: str = "other"
    analogs_carry_typical: bool = True
    central: float = 0.0
    low: float = 0.0
    high: float = 0.0
    driver: str = ""
    status: str = "open"
    source: str = ""


@dataclass
class Method:
    """Another way to price an option (Step 10). Value in USD million."""

    name: str
    value: float
    judgment_calls: int
    note: str = ""


@dataclass
class BrownfieldShares:
    """Inputs for the block-by-block brownfield method (Steps 10 and 11).

    Each share is the part of that greenfield block the existing site does
    NOT provide, so the new project must build it. Every share is a judgment
    call until site data exists.
    """

    utilities: float = 0.5
    site_works: float = 0.3
    storage_marine: float = 0.0
    tie_ins_musd: float = 0.0


@dataclass
class EstimateBasis:
    # ------------------------------------------------ Step 1: key inputs
    purpose: str = "screen"
    facility_type: str = F.LIQUEFACTION
    train_size_mtpa: float = 5.0
    trains: int = 1
    site_type: str = "greenfield"
    location_name: str = "Target site"
    target_region: str = ""
    location_group: str = "usa"
    location_steps: int = 0
    location_factor: float | None = None  # overrides group and steps
    estimate_year: int = 2026
    report_currency: str = "USD"
    report_fx: float = 1.0  # local currency units per USD
    feed_gas: str = "lean"
    co2_sequestration: bool = False
    process_family: str = "not_chosen"
    battery_limits: tuple[str, ...] = F.DEFAULT_BATTERY_LIMITS
    class_low: float = F.CLASS_5_DEFAULT[0]
    class_high: float = F.CLASS_5_DEFAULT[1]

    # ------------------------------------------------ Step 2: analog selection
    train_band: tuple[float, float] | None = (0.5, 2.0)
    fid_window_years: int | None = 15
    scopes: tuple[str, ...] = ("plant_only", "plant_plus_pipeline")
    use_plant_splits: bool = True
    site_types_allowed: tuple[str, ...] | None = None
    cluster_rule: bool = True
    process_family_filter: bool = False
    min_count_warn: int = 5
    min_count_stop: int = 3
    exclude_ids: tuple[str, ...] = ()

    # ------------------------------------------------ Step 3: adjustment method
    adjustment_method: str = "multiply"  # multiply | hybrid
    hybrid_step_share: float = F.STORAGE_MARINE_SHARE_OF_EPC

    # ------------------------------------------------ Step 4: escalation
    escalation_mode: str = "auto"  # auto | constant | index | damped | two_cases
    escalation_rate: float = F.DEFAULT_ESCALATION_RATE
    escalation_rate_low: float = 0.02
    cost_index: dict[int, float] | None = None
    index_name: str = "CEPCI"
    damping_f: float = F.DEFAULT_DAMPING_F
    two_case_high: str = "index"  # index | damped | constant | constant_low
    two_case_low: str = "damped"

    # ------------------------------------------------ Step 5: location
    location_method: str = "full"  # full | construction_share
    construction_share: float = F.CONSTRUCTION_SHARE
    location_groups: dict[str, float] = field(
        default_factory=lambda: {k: v[0] for k, v in F.LOCATION_GROUPS.items()}
    )
    analog_location_overrides: dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------ Step 6: scope and complexity
    apply_owner_costs: bool = True
    owner_cost_factor: float = F.OWNER_COST_FACTOR
    apply_site_factor: bool = True
    site_factors: dict[str, float] = field(default_factory=lambda: dict(F.SITE_TO_GREENFIELD))
    apply_multi_train: bool = True
    multi_train_factor: float = F.MULTI_TRAIN_FACTOR
    gas_method: str = "simple"  # simple | graded | off
    gas_factors_simple: dict[str, float] = field(default_factory=lambda: dict(F.GAS_FACTORS_SIMPLE))
    gas_factors_graded: dict[str, float] = field(default_factory=lambda: dict(F.GAS_FACTORS_GRADED))
    apply_co2_removal: bool = True
    co2_adder: tuple[float, float, float] = F.CO2_ADDER_USD_PER_TPA

    # ------------------------------------------------ Step 7: size scaling
    exponent: float | None = None  # None = default for the facility type
    use_fitted_exponent: bool = False
    extrapolation_limit: float = F.EXTRAPOLATION_LIMIT
    multi_train_method: str = "reverse_factor"  # reverse_factor | build_up | plant_capacity
    repeat_train_factor: float = F.REPEAT_TRAIN_FACTOR

    # ------------------------------------------------ Step 8: combining
    weighting: str = "judgment"  # judgment | rubric | size | equal
    weights: dict[str, int] = field(default_factory=dict)
    weight_reasons: dict[str, str] = field(default_factory=dict)
    drop_reasons: dict[str, str] = field(default_factory=dict)  # drop these analogs
    outlier_threshold: float = F.OUTLIER_THRESHOLD

    # ------------------------------------------------ Step 9: site items
    site_items: list[SiteItem] = field(default_factory=list)
    materiality: float = F.MATERIALITY

    # ------------------------------------------------ Step 10: variants
    methods: list[Method] = field(default_factory=list)
    analog_method_judgment_calls: int = 1
    base_rule: str = "combined"  # combined | fewest | middle | conservative
    brownfield_shares: BrownfieldShares | None = None
    method_gap_note: str = ""

    # ------------------------------------------------ Step 12: range
    range_method: str = "built"  # built | class_band | analog_spread
    definition_growth: tuple[float, float] = F.DEFINITION_GROWTH
    contingency_rate: float = F.CONTINGENCY_RATE
    widen_to_class_band: bool = False

    # ------------------------------------------------ audit trail
    option_name: str = "Option A"
    reasons: dict[str, str] = field(default_factory=dict)  # switch key or "step:N"
    log_date: str = field(default_factory=lambda: date.today().isoformat())

    # ------------------------------------------------ helpers
    @property
    def capacity_mtpa(self) -> float:
        return self.train_size_mtpa * self.trains

    @property
    def is_liquefaction(self) -> bool:
        return self.facility_type == F.LIQUEFACTION

    def resolved_exponent(self) -> float:
        if self.exponent is not None:
            return self.exponent
        return F.DEFAULT_EXPONENTS.get(self.facility_type, 0.7)

    def target_location_factor(self) -> float:
        if self.location_factor is not None:
            return self.location_factor
        base = self.location_groups.get(self.location_group, 1.0)
        return base + F.LOCATION_STEP * self.location_steps

    def with_changes(self, **changes) -> "EstimateBasis":
        return replace(self, **changes)


PREVIEW_DEFAULTS = dict(
    train_band=None,
    fid_window_years=None,
    min_count_warn=3,
    min_count_stop=1,
    apply_site_factor=False,
    apply_multi_train=False,
    gas_method="off",
    apply_co2_removal=False,
    location_group="not_set",
    use_plant_splits=True,
)


def make_basis(facility_type: str = F.LIQUEFACTION, **changes) -> EstimateBasis:
    """A basis with the right defaults for the facility type."""
    base = EstimateBasis(facility_type=facility_type)
    if facility_type != F.LIQUEFACTION:
        site = next(iter(F.SITE_TYPES[facility_type]))
        base = replace(base, site_type=site, **PREVIEW_DEFAULTS)
    base = replace(base, **changes)
    if facility_type == "flng" and "site_types_allowed" not in changes:
        # Guideline Section 18: newbuild and conversion are separate clusters.
        base = replace(base, site_types_allowed=(base.site_type,))
    return base


# ---------------------------------------------------------------- switch registry
REQUIRED_INPUTS = {"purpose", "facility_type", "train_size_mtpa", "trains", "site_type", "location_group"}

# (key, step, label, source of default)
SWITCHES = [
    ("purpose", 1, "Purpose of the estimate", "Required input"),
    ("facility_type", 1, "Facility type", "Required input"),
    ("train_size_mtpa", 1, "Capacity per train (MTPA)", "Required input"),
    ("trains", 1, "Number of trains", "Required input"),
    ("site_type", 1, "Site type", "Required input"),
    ("location_group", 1, "Location group", "Required input; OIES groups"),
    ("location_steps", 1, "Location steps of 0.10", "Guideline step rule"),
    ("location_factor", 1, "Location factor override", "None"),
    ("estimate_year", 1, "Estimate year", "Current year"),
    ("feed_gas", 1, "Feed gas", "Lean"),
    ("co2_sequestration", 1, "CO2 sequestration at target", "No"),
    ("process_family", 1, "Process family", "Not yet chosen"),
    ("battery_limits", 1, "Battery limits", "All except upstream and pipeline"),
    ("class_low", 1, "Accuracy target, low", F.AACE),
    ("class_high", 1, "Accuracy target, high", F.AACE),
    ("train_band", 2, "Train size band (times target)", "Keeps exponent effect within about 20%"),
    ("fid_window_years", 2, "FID within (years)", "Older costs need large escalation"),
    ("scopes", 2, "Scopes accepted", "A number without a stated scope cannot be normalized"),
    ("use_plant_splits", 2, "Use published plant-only splits", F.OIES),
    ("site_types_allowed", 2, "Site types accepted", "Both, adjusted in Step 6"),
    ("cluster_rule", 2, "Separate cluster below 1 and above 6 MTPA per train", F.GUIDE),
    ("process_family_filter", 2, "Same process family only", "No reliable capex factor between cycles"),
    ("min_count_warn", 2, "Warn below this many analogs", F.GUIDE),
    ("min_count_stop", 2, "Stop below this many analogs", F.GUIDE),
    ("exclude_ids", 2, "Analogs excluded by the user", "None"),
    ("adjustment_method", 3, "Adjustment method", "Multiply at Class 5"),
    ("hybrid_step_share", 3, "Hybrid: storage and marine share removed from analogs", F.JUDGMENT),
    ("escalation_mode", 4, "Escalation method", "Two cases if an index is loaded, else 3%"),
    ("escalation_rate", 4, "Constant escalation rate", F.JUDGMENT),
    ("escalation_rate_low", 4, "Low constant rate (two cases)", F.JUDGMENT),
    ("index_name", 4, "Cost index", "CEPCI (user loads values)"),
    ("damping_f", 4, "Damping fraction f", "Guideline test case"),
    ("two_case_high", 4, "High escalation case", F.GUIDE),
    ("two_case_low", 4, "Low escalation case", F.GUIDE),
    ("location_method", 5, "Location method", F.OIES),
    ("construction_share", 5, "Construction share (split method)", F.OIES),
    ("location_groups", 5, "Location group factors", F.OIES),
    ("analog_location_overrides", 5, "Analog location overrides", "None"),
    ("apply_owner_costs", 6, "Owner's costs on EPC-only figures", F.GUIDE),
    ("owner_cost_factor", 6, "Owner's cost factor", "User input; OIES uses 10%"),
    ("apply_site_factor", 6, "Site type adjustment", F.OIES),
    ("site_factors", 6, "Site type factors", F.OIES + "; partial by judgment"),
    ("apply_multi_train", 6, "Multi-train to one train", F.OIES),
    ("multi_train_factor", 6, "Multi-train factor", F.OIES),
    ("gas_method", 6, "Gas complexity method", F.OIES),
    ("apply_co2_removal", 6, "Remove CO2 sequestration from analogs", F.OIES),
    ("exponent", 7, "Size exponent n", "Common practice"),
    ("use_fitted_exponent", 7, "Use the fitted exponent", "No: do not derive n from a small set"),
    ("extrapolation_limit", 7, "Extrapolation warning limit", F.GUIDE),
    ("multi_train_method", 7, "Multi-train target method", F.GUIDE),
    ("repeat_train_factor", 7, "Repeat train factor (build-up)", F.OIES),
    ("weighting", 8, "Weighting method", "Judgment prompted by the rubric"),
    ("outlier_threshold", 8, "Outlier flag threshold", F.GUIDE),
    ("materiality", 9, "Materiality threshold", F.GUIDE),
    ("base_rule", 10, "Rule for choosing the base method", F.GUIDE),
    ("analog_method_judgment_calls", 10, "Judgment calls in the analog method", F.GUIDE),
    ("range_method", 12, "Range method", "Built from named uncertainties"),
    ("definition_growth", 12, "Definition growth", F.GUIDE),
    ("contingency_rate", 12, "Contingency rate for the non-budget share", F.JUDGMENT),
    ("widen_to_class_band", 12, "Widen range to the class band", "No; warn instead"),
]


def _show(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (tuple, list)):
        return ", ".join(_show(v) for v in value) if value else "None"
    if isinstance(value, dict):
        return "; ".join(f"{k}={_show(v)}" for k, v in value.items()) if value else "None"
    return str(value)


def decision_log(basis: EstimateBasis) -> list[dict]:
    """One row per switch: setting, default, reason, date. Defaults included."""
    default = make_basis(basis.facility_type, site_type=basis.site_type)
    rows = []
    for key, step, label, source in SWITCHES:
        setting = getattr(basis, key)
        required = key in REQUIRED_INPUTS
        dflt = "No default" if required else getattr(default, key)
        if key == "exponent":
            setting, dflt = basis.resolved_exponent(), default.resolved_exponent()
        changed = (not required) and setting != dflt
        reason = basis.reasons.get(key) or basis.reasons.get(f"step:{step}") or ""
        if not reason:
            if required:
                reason = "Required input"
            elif not changed:
                reason = "Default accepted"
        rows.append(
            {
                "step": step,
                "switch": label,
                "setting": _show(setting),
                "default": _show(dflt),
                "changed": changed,
                "source_of_default": source,
                "reason": reason,
                "date": basis.log_date,
            }
        )
    if basis.cost_index:
        rows.append({
            "step": 4, "switch": "Cost index values", "setting": f"{len(basis.cost_index)} years loaded",
            "default": "None", "changed": True, "source_of_default": "User",
            "reason": basis.reasons.get("cost_index", basis.reasons.get("step:4", "")), "date": basis.log_date,
        })
    for aid, w in basis.weights.items():
        rows.append({
            "step": 8, "switch": f"Weight for {aid}", "setting": str(w), "default": "Rubric suggestion",
            "changed": True, "source_of_default": "Rubric",
            "reason": basis.weight_reasons.get(aid, ""), "date": basis.log_date,
        })
    for aid, why in basis.drop_reasons.items():
        rows.append({
            "step": 8, "switch": f"Drop {aid}", "setting": "Dropped", "default": "Kept",
            "changed": True, "source_of_default": "-", "reason": why, "date": basis.log_date,
        })
    for item in basis.site_items:
        rows.append({
            "step": 9, "switch": f"Site item: {item.name}",
            "setting": f"central {item.central:g}, low {item.low:g}, high {item.high:g}",
            "default": "None", "changed": True, "source_of_default": item.source or "User",
            "reason": item.driver, "date": basis.log_date,
        })
    return rows


def field_names() -> list[str]:
    return [f.name for f in fields(EstimateBasis)]
