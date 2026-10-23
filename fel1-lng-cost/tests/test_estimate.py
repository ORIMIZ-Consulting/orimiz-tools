import math

import pandas as pd
import pytest

from fel1_lng_cost import EstimateBasis, check_analogues, estimate, load_analogues, to_excel_bytes
from fel1_lng_cost.estimate import escalation_factor, weighted_quantile


def one_analogue(**overrides):
    row = dict(
        id="a", project="Test plant", country="X", region="R", facility_type="onshore_liquefaction",
        site_type="greenfield", capacity_mtpa=10.0, cost_amount_million=10000, currency="USD",
        fx_to_usd=1.0, cost_year=2020, scope="plant_only", source_url="https://example.com",
        cost_usd_million=10000.0, notes="",
    )
    row.update(overrides)
    return pd.DataFrame([row])


def test_public_data_loads_and_is_clean():
    df = load_analogues()
    assert len(df) >= 20
    assert check_analogues(df).ok
    assert set(df["facility_type"]) == {"onshore_liquefaction", "flng", "onshore_regas", "fsru"}


def test_escalation_rate_and_index():
    assert escalation_factor(2020, 2020, 0.03) == 1.0
    assert escalation_factor(2020, 2022, 0.03) == pytest.approx(1.0609)
    assert escalation_factor(2020, 2022, 0.03, {2020: 100, 2022: 125}) == pytest.approx(1.25)


def test_same_size_same_year_returns_analogue_cost():
    basis = EstimateBasis("onshore_liquefaction", 10.0, estimate_year=2020)
    res = estimate(one_analogue(), basis)
    assert res.p50_usd_million == pytest.approx(10000)


def test_size_scaling_uses_exponent():
    basis = EstimateBasis("onshore_liquefaction", 20.0, estimate_year=2020, scale_exponent=0.7)
    res = estimate(one_analogue(), basis)
    assert res.p50_usd_million == pytest.approx(10000 * 2 ** 0.7)
    assert res.analogues.loc[0, "weight"] == pytest.approx(0.5)


def test_location_adjustment():
    basis = EstimateBasis(
        "onshore_liquefaction", 10.0, estimate_year=2020,
        target_location_factor=1.2, region_location_factors={"R": 0.8},
    )
    res = estimate(one_analogue(), basis)
    assert res.p50_usd_million == pytest.approx(10000 * 1.5)


def test_class_band_sets_minimum_range():
    basis = EstimateBasis("onshore_liquefaction", 10.0, estimate_year=2020,
                          class_low=-0.3, class_high=0.5)
    res = estimate(one_analogue(), basis)
    assert res.p10_usd_million == pytest.approx(7000)
    assert res.p90_usd_million == pytest.approx(15000)
    assert any("Only 1" in w for w in res.warnings)


def test_weighted_quantile_median():
    assert weighted_quantile([1, 2, 3], [1, 1, 1], 0.5) == pytest.approx(2)
    assert weighted_quantile([1, 3], [3, 1], 0.5) < 2


def test_scope_filter_excludes_integrated_by_default():
    df = load_analogues()
    res = estimate(df, EstimateBasis("onshore_liquefaction", 12.0))
    assert "integrated_upstream" not in set(res.analogues["scope"])


def test_every_facility_type_runs_and_orders_results():
    df = load_analogues()
    for ftype, cap in [("onshore_liquefaction", 12), ("flng", 3), ("onshore_regas", 5), ("fsru", 5)]:
        res = estimate(df, EstimateBasis(ftype, cap))
        assert res.p10_usd_million < res.p50_usd_million < res.p90_usd_million
        assert math.isfinite(res.p50_unit_cost_usd_per_tpa)


def test_no_match_raises():
    with pytest.raises(ValueError):
        estimate(one_analogue(), EstimateBasis("flng", 3.0))


def test_bad_rows_are_caught():
    bad = one_analogue(facility_type="spaceport", capacity_mtpa=-1)
    errors = check_analogues(bad).errors
    assert any("facility_type" in e for e in errors)
    assert any("capacity_mtpa" in e for e in errors)


def test_private_file_overrides_public(tmp_path):
    pub = load_analogues()
    row = pub[pub["id"] == "cameron_lng"].drop(
        columns=["data_source", "cost_usd_million", "unit_cost_usd_per_tpa"]
    ).copy()
    row["cost_amount_million"] = 12345
    path = tmp_path / "private_test.csv"
    row.to_csv(path, index=False)
    df = load_analogues(path)
    assert len(df) == len(pub)
    assert df.loc[df["id"] == "cameron_lng", "cost_usd_million"].item() == 12345


def test_excel_export_is_valid():
    res = estimate(load_analogues(), EstimateBasis("onshore_liquefaction", 12.0))
    data = to_excel_bytes(res)
    assert data[:2] == b"PK"
