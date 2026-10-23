"""Load and check analogue project data.

An analogue is a past project with a known cost. Each row in the analogue
file records what was built, how big it was, what it cost, in which year and
currency, what the cost covers (its scope), and where the figure came from.

The tool ships with a public set in ``data/public_analogues.csv``. You can
add your own projects in a separate private file with the same columns.
Files whose names start with ``private_`` are ignored by git, so they are
never uploaded to GitHub.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PUBLIC_FILE = DATA_DIR / "public_analogues.csv"

FACILITY_TYPES = {
    "onshore_liquefaction": "Onshore liquefaction",
    "flng": "Floating liquefaction (FLNG)",
    "onshore_regas": "Onshore regasification terminal",
    "fsru": "Floating storage and regasification unit (FSRU)",
}

SCOPES = {
    "plant_only": "Plant only (EPC, owner costs, contingency)",
    "plant_plus_pipeline": "Plant plus its own feed pipeline",
    "integrated_upstream": "Plant plus upstream field development",
    "unclear": "Scope not clear from the source",
}

# Scopes that are comparable with a plant-only estimate by default.
DEFAULT_SCOPES = ("plant_only", "plant_plus_pipeline")

REQUIRED_COLUMNS = [
    "id",
    "project",
    "country",
    "region",
    "facility_type",
    "site_type",
    "capacity_mtpa",
    "cost_amount_million",
    "currency",
    "fx_to_usd",
    "cost_year",
    "scope",
    "source_url",
]


@dataclass
class AnalogueCheck:
    """Problems found in an analogue file. Empty lists mean the file is fine."""

    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def check_analogues(df: pd.DataFrame) -> AnalogueCheck:
    """Return errors (must fix) and warnings (worth a look) for a table."""
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing columns: {', '.join(missing)}")
        return AnalogueCheck(errors, warnings)

    if df["id"].duplicated().any():
        dupes = sorted(df.loc[df["id"].duplicated(), "id"].unique())
        errors.append(f"Duplicate ids: {', '.join(dupes)}")

    for _, row in df.iterrows():
        rid = row["id"]
        if row["facility_type"] not in FACILITY_TYPES:
            errors.append(f"{rid}: unknown facility_type '{row['facility_type']}'")
        if row["scope"] not in SCOPES:
            errors.append(f"{rid}: unknown scope '{row['scope']}'")
        for col in ("capacity_mtpa", "cost_amount_million", "fx_to_usd"):
            value = row[col]
            if pd.isna(value) or float(value) <= 0:
                errors.append(f"{rid}: {col} must be a positive number")
        year = row["cost_year"]
        if pd.isna(year) or not 1990 <= int(year) <= 2100:
            errors.append(f"{rid}: cost_year looks wrong ({year})")
        if pd.isna(row["source_url"]) or not str(row["source_url"]).startswith("http"):
            warnings.append(f"{rid}: no source link")

    return AnalogueCheck(errors, warnings)


def load_analogues(*paths: str | Path, include_public: bool = True) -> pd.DataFrame:
    """Load the public set and any extra files into one table.

    Rows from later files replace public rows that share the same ``id``,
    so you can correct a public figure in your private file.
    """
    frames = []
    if include_public:
        public = pd.read_csv(PUBLIC_FILE)
        public["data_source"] = "public"
        frames.append(public)
    for path in paths:
        # Accepts a file path or an open file (such as a web upload).
        extra = pd.read_csv(path)
        extra["data_source"] = Path(getattr(path, "name", str(path))).name
        frames.append(extra)
    if not frames:
        raise ValueError("No analogue data: include the public set or give a file.")

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="id", keep="last").reset_index(drop=True)

    result = check_analogues(df)
    if not result.ok:
        raise ValueError("Analogue data has problems:\n" + "\n".join(result.errors))

    df["cost_usd_million"] = df["cost_amount_million"] * df["fx_to_usd"]
    df["unit_cost_usd_per_tpa"] = df["cost_usd_million"] / df["capacity_mtpa"]
    df["cost_year"] = df["cost_year"].astype(int)
    return df
