"""Load and check analog project data (guideline Step 2 record format).

An analog is a past project with a published cost. Each row records what was
built, how big it was, what the figure covers, when and in what currency, the
source, and a data-quality note.

The public set is ``data/public_analogs.csv``. Add your own projects in a file
with the same columns whose name starts with ``private_``: git ignores those
files, so they never reach GitHub. A row with the same ``id`` as a public row
replaces it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import factors as F

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PUBLIC_FILE = DATA_DIR / "public_analogs.csv"

REQUIRED_COLUMNS = [
    "id", "project", "country", "region", "location_group", "location_steps",
    "facility_type", "site_type", "trains", "capacity_mtpa", "fid_year", "cost_year",
    "cost_amount_million", "currency", "fx_to_usd", "cost_basis", "scope",
    "liquids_scope", "contingency_status", "source_url",
]
OPTIONAL_DEFAULTS = {
    "train_size_mtpa": None,
    "plant_only_amount_million": None,
    "split_source": "",
    "gas_adjust": "yes",
    "co2_sequestration": "no",
    "process_family": "not_stated",
    "epc_contractor": "",
    "contracting_basis": "unknown",
    "data_quality": "C",
    "notes": "",
}
LIQUIDS = ("lean", "rich", "lpg", "condensate", "sulphur", "unknown")


@dataclass
class AnalogCheck:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _yes(value) -> bool:
    return str(value).strip().lower() in ("yes", "y", "true", "1")


def check_analogs(df: pd.DataFrame) -> AnalogCheck:
    """Errors must be fixed; warnings are worth a look."""
    errors: list[str] = []
    warnings: list[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return AnalogCheck([f"Missing columns: {', '.join(missing)}"], warnings)
    if df["id"].duplicated().any():
        errors.append("Duplicate ids: " + ", ".join(sorted(df.loc[df["id"].duplicated(), "id"])))

    for _, r in df.iterrows():
        rid = r["id"]
        ftype = r["facility_type"]
        if ftype not in F.FACILITY_TYPES:
            errors.append(f"{rid}: unknown facility_type '{ftype}'")
            continue
        if r["site_type"] not in F.SITE_TYPES[ftype]:
            errors.append(f"{rid}: site_type '{r['site_type']}' is not valid for {ftype}")
        if r["scope"] not in F.SCOPES:
            errors.append(f"{rid}: unknown scope '{r['scope']}'")
        if r["cost_basis"] not in F.COST_BASIS:
            errors.append(f"{rid}: unknown cost_basis '{r['cost_basis']}'")
        if r["contingency_status"] not in F.CONTINGENCY_STATUS:
            errors.append(f"{rid}: unknown contingency_status '{r['contingency_status']}'")
        if r["liquids_scope"] not in LIQUIDS:
            errors.append(f"{rid}: unknown liquids_scope '{r['liquids_scope']}'")
        if r["location_group"] not in F.LOCATION_GROUPS:
            warnings.append(f"{rid}: location group '{r['location_group']}' not in the library; 1.00 used")
        for col in ("capacity_mtpa", "cost_amount_million", "fx_to_usd", "trains"):
            v = r[col]
            if pd.isna(v) or float(v) <= 0:
                errors.append(f"{rid}: {col} must be a positive number")
        for col in ("fid_year", "cost_year"):
            v = r[col]
            if pd.isna(v) or not 1990 <= int(v) <= 2100:
                errors.append(f"{rid}: {col} looks wrong ({v})")
        split = r.get("plant_only_amount_million")
        if split is not None and not pd.isna(split) and float(split) > float(r["cost_amount_million"]):
            errors.append(f"{rid}: plant-only amount is larger than the total")
        if not str(r["source_url"]).startswith("http"):
            warnings.append(f"{rid}: no source link")
    return AnalogCheck(errors, warnings)


def _cluster(train_size: float) -> str:
    small, large = F.SIZE_CLUSTERS
    if train_size < small:
        return "small"
    if train_size > large:
        return "large"
    return "standard"


def load_analogs(*paths, include_public: bool = True) -> pd.DataFrame:
    """Load the public set plus any extra files (paths or open files)."""
    frames = []
    if include_public:
        pub = pd.read_csv(PUBLIC_FILE)
        pub["data_source"] = "public"
        frames.append(pub)
    for path in paths:
        extra = pd.read_csv(path)
        extra["data_source"] = Path(getattr(path, "name", str(path))).name
        frames.append(extra)
    if not frames:
        raise ValueError("No analog data: include the public set or give a file.")
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="id", keep="last").reset_index(drop=True)

    for col, default in OPTIONAL_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
    for col in ("split_source", "epc_contractor", "notes"):
        df[col] = df[col].fillna("").astype(str)
    df["process_family"] = df["process_family"].fillna("not_stated")
    df["contracting_basis"] = df["contracting_basis"].fillna("unknown")
    df["data_quality"] = df["data_quality"].fillna("C")
    df["location_steps"] = df["location_steps"].fillna(0).astype(int)

    result = check_analogs(df)
    if not result.ok:
        raise ValueError("Analog data has problems:\n" + "\n".join(result.errors))

    df["trains"] = df["trains"].astype(int)
    df["fid_year"] = df["fid_year"].astype(int)
    df["cost_year"] = df["cost_year"].astype(int)
    size = pd.to_numeric(df["train_size_mtpa"], errors="coerce")
    df["train_size_mtpa"] = size.fillna(df["capacity_mtpa"] / df["trains"])
    df["cluster"] = df["train_size_mtpa"].map(_cluster)
    df["gas_adjust"] = df["gas_adjust"].map(_yes)
    df["co2_sequestration"] = df["co2_sequestration"].map(_yes)
    df["cost_usd_million"] = df["cost_amount_million"] * df["fx_to_usd"]
    split = pd.to_numeric(df["plant_only_amount_million"], errors="coerce")
    df["plant_usd_million"] = split * df["fx_to_usd"]
    df["unit_cost_reported"] = df["cost_usd_million"] / df["capacity_mtpa"]
    return df
