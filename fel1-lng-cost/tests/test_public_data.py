"""Checks on the public analog set, the outputs and the app."""
from pathlib import Path

import pytest

from fel1_lng_cost import estimate, load_analogs, make_basis, to_excel_bytes
from fel1_lng_cost.analogs import check_analogs

APP = Path(__file__).resolve().parent.parent / "app.py"


def test_public_set_is_clean_and_sourced():
    df = load_analogs()
    check = check_analogs(df)
    assert check.ok, check.errors
    assert not check.warnings, check.warnings
    assert df["source_url"].str.startswith("http").all()
    assert (df["notes"].str.len() > 0).all()
    assert (df["unit_cost_reported"] > 0).all()


def test_split_never_exceeds_total():
    df = load_analogs()
    split = df.dropna(subset=["plant_usd_million"])
    assert (split["plant_usd_million"] <= split["cost_usd_million"]).all()


@pytest.mark.parametrize("ftype,size,site", [
    ("onshore_liquefaction", 5.0, "greenfield"),
    ("onshore_liquefaction", 4.0, "brownfield"),
    ("flng", 2.5, "conversion"),
    ("flng", 2.0, "newbuild"),
    ("onshore_regas", 5.0, "greenfield"),
    ("fsru", 5.0, "newbuild"),
])
def test_every_type_runs(ftype, size, site):
    res = estimate(load_analogs(), make_basis(ftype, train_size_mtpa=size, site_type=site))
    assert res.low <= res.central <= res.high
    assert to_excel_bytes(res)[:2] == b"PK"


def test_liquefaction_default_uses_enough_analogs():
    res = estimate(load_analogs(), make_basis(train_size_mtpa=5.0, trains=2))
    assert res.stats["count"] >= 10


def test_app_runs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    assert len(at.metric) >= 4
