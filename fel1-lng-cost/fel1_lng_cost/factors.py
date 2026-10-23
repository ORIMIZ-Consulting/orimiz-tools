"""Factor libraries: every default the method uses, with its source.

Each number here is a default only. The user can change any of them through
``EstimateBasis``. Section numbers refer to docs/GUIDELINE.md.

Main sources:
- OIES: Songhurst, B. (2018). LNG Plant Cost Reduction 2014-18. Oxford
  Institute for Energy Studies, Paper NG137.
- AACE: AACE International Recommended Practice 18R-97.
- KBR (2007), as adjusted by OIES to a whole-plant basis.

Where no public source exists, the value is labelled "judgment".
"""
from __future__ import annotations

OIES = "Songhurst (2018), LNG Plant Cost Reduction 2014-18, OIES Paper NG137"
OIES_URL = (
    "https://www.oxfordenergy.org/wpcms/wp-content/uploads/2018/10/"
    "LNG-Plant-Cost-Reduction-2014%E2%80%9318-NG137.pdf"
)
AACE = "AACE International Recommended Practice 18R-97"
KBR = "KBR (2007), LNG Liquefaction: Not All Plants Are Created Equal, adjusted by OIES"
GUIDE = "FEL 1 LNG Capital Cost Estimating Guideline v0.1"
JUDGMENT = "Judgment (no public source)"

# ---------------------------------------------------------------- facility types
FACILITY_TYPES = {
    "onshore_liquefaction": "Onshore liquefaction",
    "flng": "Floating liquefaction (FLNG), preview",
    "onshore_regas": "Onshore regasification terminal, preview",
    "fsru": "FSRU, preview",
}
LIQUEFACTION = "onshore_liquefaction"

SITE_TYPES = {
    "onshore_liquefaction": {
        "greenfield": "Greenfield: new site with its own tanks, jetty and utilities",
        "greenfield_industrial": "Greenfield on an existing industrial site (partly brownfield)",
        "brownfield_partial": "Brownfield, partial: shares some of tanks, jetty or utilities",
        "brownfield": "Brownfield: train added to an existing site",
    },
    "flng": {"newbuild": "Newbuild FLNG", "conversion": "Converted LNG carrier"},
    "onshore_regas": {"greenfield": "Greenfield terminal"},
    "fsru": {"newbuild": "Newbuild FSRU"},
}

SCOPES = {
    "plant_only": "Plant only",
    "plant_plus_pipeline": "Plant plus its own feed pipeline",
    "integrated_upstream": "Plant plus upstream field development",
    "unclear": "Scope not clear from the source",
}

COST_BASIS = {
    "budget": "Sanctioned budget or total investment at FID",
    "outturn": "Final or latest reported cost",
    "epc": "EPC contract value only",
    "financing": "Financing package (may include financing costs)",
    "estimate": "Estimate or derived figure",
}

CONTINGENCY_STATUS = {
    "budget": "Sanctioned budget (contains contingency)",
    "epc_only": "EPC only (no owner's contingency)",
    "unknown": "Unknown",
}

PROCESS_FAMILIES = {
    "not_chosen": "Not yet chosen",
    "c3mr": "C3MR (propane pre-cooled mixed refrigerant)",
    "dmr": "DMR (dual mixed refrigerant)",
    "optimized_cascade": "Optimized Cascade",
    "smr": "SMR (single mixed refrigerant)",
    "nitrogen_expander": "Nitrogen expander",
    "other": "Other",
    "not_stated": "Not stated",
}

FEED_GAS = {
    "lean": "Lean",
    "rich": "Rich (LPG, condensate)",
    "lpg": "Rich, with LPG recovery",
    "condensate": "Rich, with condensate recovery",
    "sulphur": "Sour, with sulphur recovery",
}

PURPOSES = {
    "screen": "Screen an idea",
    "compare": "Compare options",
    "gate1": "Gate 1 decision",
}

BATTERY_LIMIT_ITEMS = {
    "trains": "Liquefaction trains",
    "utilities": "Utilities and offsites",
    "tanks": "Storage tanks",
    "marine": "Jetty and marine",
    "site_works": "Site works",
    "owners_costs": "Owner's costs",
    "upstream": "Upstream",
    "pipeline": "Feed pipeline",
}
DEFAULT_BATTERY_LIMITS = ("trains", "utilities", "tanks", "marine", "site_works", "owners_costs")

# ---------------------------------------------------------------- Step 4
DEFAULT_ESCALATION_RATE = 0.03  # fallback only; judgment
DEFAULT_DAMPING_F = 0.5  # guideline test case

# ---------------------------------------------------------------- Step 5
# Location factor groups, USA = 1.00. OIES Figure 5; "remote" from OIES text.
LOCATION_GROUPS = {
    "usa": (1.00, "USA"),
    "yamal": (1.25, "Yamal (Russian Arctic)"),
    "png": (1.29, "Papua New Guinea"),
    "queensland": (1.34, "Queensland"),
    "nw_australia": (1.72, "North West Australia"),
    "remote": (1.30, "Remote site"),
    "not_set": (1.00, "Not set (no adjustment)"),
}
LOCATION_STEP = 0.10  # guideline step rule; judgment
CONSTRUCTION_SHARE = 0.32  # OIES Table 5

# ---------------------------------------------------------------- Step 6
OWNER_COST_FACTOR = 1.09  # editable 1.08 to 1.12; OIES uses 10%
# Factor that brings each site type to a greenfield basis.
SITE_TO_GREENFIELD = {
    "greenfield": 1.00,
    "greenfield_industrial": 1.15,  # OIES group adjustment (partly brownfield site)
    "brownfield_partial": 1.25,  # judgment
    "brownfield": 1.50,  # OIES: add 50% for tanks, jetty and utilities
}
MULTI_TRAIN_FACTOR = 1.15  # OIES, Queensland plants: single unit 10-20% higher
REPEAT_TRAIN_FACTOR = 0.50  # OIES, Nigeria LNG Plus: 50% lower $/tpa for added capacity
GAS_FACTORS_SIMPLE = {"lean": 1.00, "rich": 1.10}  # OIES
GAS_FACTORS_GRADED = {"lean": 1.00, "lpg": 1.14, "condensate": 1.31, "sulphur": 1.52}  # KBR via OIES
CO2_ADDER_USD_PER_TPA = (60.0, 95.0, 130.0)  # OIES: Snohvit 60, Gorgon 130; middle is the mean
TECHNOLOGY_SENSITIVITY = 0.05  # OIES gives no reliable factor between cycles

# ---------------------------------------------------------------- Step 7
DEFAULT_EXPONENTS = {"onshore_liquefaction": 0.7, "flng": 0.7, "onshore_regas": 0.6, "fsru": 0.6}
EXPONENT_SENSITIVITY = (0.6, 0.8)
EXTRAPOLATION_LIMIT = 1.5
SIZE_CLUSTERS = (1.0, 6.0)  # MTPA per train; small below, large above

# ---------------------------------------------------------------- Step 8
RUBRIC = (
    ("same_region", "Same region as the target"),
    ("clean_figure", "Published plant-only figure with no assumed split"),
    ("size_close", "Train size within 1.5 times the target"),
    ("few_adjustments", "Two or fewer scope adjustments"),
    ("recent", "FID within 10 years of the estimate date"),
)


def rubric_weight(points: int) -> int:
    """Suggested weight from rubric points. The mapping is the tool's own choice."""
    if points >= 4:
        return 3
    if points >= 2:
        return 2
    return 1


OUTLIER_THRESHOLD = 0.30
STATS_GAP_WARNING = 0.05

# ---------------------------------------------------------------- Step 9
MATERIALITY = 0.01
TANK_REFERENCE = {
    "cost_musd": 200.0,
    "volume_m3": 180_000.0,
    "exponent": 0.6,
    "year": 2023,
    "source": "GATE Rotterdam tank (VINCI, 2023); Ruwais tanks (CB&I, 2025)",
}
DREDGING_USD_PER_M3 = (15.0, 30.0)  # Cuyutlan, Soyo
SITE_ITEM_CATEGORIES = ("marine", "storage", "site_preparation", "power", "co2", "other")

# ---------------------------------------------------------------- Step 11
COST_TYPE_SHARES = {
    "Owner's costs": 0.10,
    "Engineering and project management": 0.08,
    "Equipment": 0.30,
    "Bulk materials": 0.20,
    "Construction": 0.32,
}
PROCESS_SHARE_OF_EPC = 0.50  # OIES
STORAGE_MARINE_SHARE_OF_EPC = 0.08  # guideline test case; judgment
UTILITIES_SHARE_OF_REMAINDER = 0.60  # judgment

# ---------------------------------------------------------------- Step 12
CLASS_5_DEFAULT = (-0.30, 0.50)
DEFINITION_GROWTH = (0.0, 0.15)
CONTINGENCY_RATE = 0.15  # judgment; the guideline gives no default
AACE_CLASSES = (
    ("5", "0% to 2%", "Capacity factoring, analog curves", "-20% to -50%", "+30% to +100%"),
    ("4", "1% to 15%", "Equipment factoring, parametric models", "-15% to -30%", "+20% to +50%"),
    ("3", "10% to 40%", "Semi-detailed unit costs", "-10% to -20%", "+10% to +30%"),
)

# ---------------------------------------------------------------- references
FACTOR_REFERENCES = [
    ("Location groups (USA 1.00 to NW Australia 1.72)", OIES, OIES_URL),
    ("Cost type split (owner 10%, engineering 8%, equipment 30%, bulks 20%, construction 32%)", OIES, OIES_URL),
    ("Brownfield to greenfield x1.50", OIES, OIES_URL),
    ("Partly brownfield site x1.15", OIES + " (group adjustment)", OIES_URL),
    ("Partial brownfield x1.25", JUDGMENT, ""),
    ("Multi-train to one train x1.15", OIES + " (Queensland plants)", OIES_URL),
    ("Repeat train factor 0.5", OIES + " (Nigeria LNG Plus)", OIES_URL),
    ("Rich gas x1.10", OIES, OIES_URL),
    ("Graded gas factors 1.14 / 1.31 / 1.52", KBR, OIES_URL),
    ("CO2 sequestration USD 60 to 130 per tpa", OIES + " (Snohvit, Gorgon)", OIES_URL),
    ("Owner's costs x1.09 on EPC-only figures", GUIDE + "; OIES uses 10%", OIES_URL),
    ("Size exponent 0.7 (0.6 for regas)", "Common practice (six-tenths rule and variants)", ""),
    ("Class 5 range -30% / +50%", AACE, ""),
    ("Definition growth 0 / +15%", GUIDE + " (Donggi-Senoro, PNG LNG growth)", ""),
    ("Storage tank about USD 200m per 180,000 m3", TANK_REFERENCE["source"], ""),
    ("Dredging USD 15 to 30 per m3", "Cuyutlan (Dredging Today, 2010); Soyo (SWZ Maritime, 2010)", ""),
    ("Location step 0.10", GUIDE + "; judgment", ""),
    ("Storage and marine 8% of EPC; utilities 60% of remainder", JUDGMENT, ""),
    ("Contingency rate 15% for the non-budget share", JUDGMENT, ""),
    ("Rubric points to weight: 0-1 = 1, 2-3 = 2, 4-5 = 3", JUDGMENT + " (tool's mapping)", ""),
]
