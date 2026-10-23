"""Checks of each guideline step on small hand-made analog sets."""
import math

import pandas as pd
import pytest

from fel1_lng_cost import (
    BrownfieldShares, Method, SiteItem, choose_base, compare_options, escalation_factor,
    estimate, load_analogs, make_basis, tank_cost,
)
from fel1_lng_cost.analogs import check_analogs

BASE_ROW = dict(
    id="a1", project="Analog 1", country="USA", region="North America", location_group="usa",
    location_steps=0, facility_type="onshore_liquefaction", site_type="greenfield", trains=1,
    capacity_mtpa=5.0, train_size_mtpa="", fid_year=2020, cost_year=2020, cost_amount_million=5000,
    currency="USD", fx_to_usd=1.0, cost_basis="budget", scope="plant_only",
    plant_only_amount_million="", split_source="", liquids_scope="lean", gas_adjust="yes",
    co2_sequestration="no", process_family="c3mr", epc_contractor="Builder", contracting_basis="lump_sum",
    contingency_status="budget", data_quality="A", source_url="https://example.com", notes="",
)


def analogs(tmp_path, *overrides):
    rows = []
    for i, o in enumerate(overrides):
        row = dict(BASE_ROW, id=f"a{i + 1}", project=f"Analog {i + 1}")
        row.update(o)
        rows.append(row)
    path = tmp_path / "private_test.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return load_analogs(path, include_public=False)


def basis(**kw):
    kw.setdefault("estimate_year", 2020)
    kw.setdefault("min_count_stop", 1)
    kw.setdefault("min_count_warn", 1)
    kw.setdefault("definition_growth", (0.0, 0.0))
    return make_basis(**kw)


def central_unit(res):
    return res.central / res.basis.capacity_mtpa


# ------------------------------------------------------------- Step 2
def test_filters_record_a_reason(tmp_path):
    df = analogs(tmp_path, {}, {"fid_year": 2000, "cost_year": 2000}, {"capacity_mtpa": 20.0},
                 {"scope": "integrated_upstream"}, {"scope": "integrated_upstream", "plant_only_amount_million": 4000})
    res = estimate(df, basis())
    notes = dict(zip(res.pool["id"], res.pool["selection_note"]))
    assert notes["a1"] == ""
    assert notes["a2"].startswith("FID before")
    assert notes["a3"].startswith("Train size outside")
    assert notes["a4"].startswith("Scope")
    assert notes["a5"] == ""  # integrated, but a plant split exists


def test_cluster_rule_for_large_trains(tmp_path):
    df = analogs(tmp_path, {"capacity_mtpa": 7.0}, {"capacity_mtpa": 5.0})
    res = estimate(df, basis(train_size_mtpa=7.5))
    notes = dict(zip(res.pool["id"], res.pool["selection_note"]))
    assert notes["a1"] == "" and "cluster" in notes["a2"]
    assert any("outside 1 to 6 MTPA" in w for w in res.warnings)


def test_minimum_count_stops(tmp_path):
    df = analogs(tmp_path, {})
    with pytest.raises(ValueError, match="minimum"):
        estimate(df, basis(min_count_stop=3))


# ------------------------------------------------------------- Step 4
def test_escalation_methods():
    b = make_basis(escalation_rate=0.03, cost_index={2015: 100.0, 2025: 150.0}, damping_f=0.5)
    assert escalation_factor(2015, 2017, "constant", b) == pytest.approx(1.03 ** 2)
    assert escalation_factor(2015, 2025, "index", b) == pytest.approx(1.5)
    assert escalation_factor(2015, 2025, "damped", b) == pytest.approx(1.25)
    with pytest.raises(ValueError):
        escalation_factor(2015, 2025, "index", make_basis())


def test_two_cases_and_central_is_midpoint(tmp_path):
    df = analogs(tmp_path, {"cost_year": 2015, "fid_year": 2015})
    b = basis(estimate_year=2025, cost_index={2015: 100.0, 2025: 150.0})
    res = estimate(df, b)
    assert set(res.cases["case"]) == {"High", "Low"}
    assert central_unit(res) == pytest.approx(1000 * (1.5 + 1.25) / 2)


def test_calibration_pair(tmp_path):
    df = analogs(tmp_path, {"cost_year": 2015, "fid_year": 2015}, {"cost_year": 2023, "fid_year": 2023,
                                                                  "cost_amount_million": 5500})
    b = basis(estimate_year=2025, cost_index={2015: 100.0, 2023: 140.0, 2025: 150.0}, fid_window_years=None)
    cal = estimate(df, b).calibration
    assert len(cal) == 1
    assert cal.loc[0, "f"] == pytest.approx((1.1 - 1) / (1.4 - 1))


# ------------------------------------------------------------- Step 5
def test_location_full_and_construction_share(tmp_path):
    df = analogs(tmp_path, {})
    full = estimate(df, basis(location_group="remote"))
    assert central_unit(full) == pytest.approx(1000 * 1.30)
    split = estimate(df, basis(location_group="remote", location_method="construction_share"))
    assert central_unit(split) == pytest.approx(1000 * (1 + 0.32 * 0.30))
    stepped = estimate(df, basis(location_group="remote", location_steps=-1))
    assert central_unit(stepped) == pytest.approx(1200)


# ------------------------------------------------------------- Step 6
def test_scope_factors(tmp_path):
    df = analogs(
        tmp_path,
        {"cost_basis": "epc", "contingency_status": "epc_only"},
        {"site_type": "brownfield"},
        {"trains": 2, "capacity_mtpa": 10.0},
        {"liquids_scope": "rich"},
        {"co2_sequestration": "yes"},
        {"scope": "integrated_upstream", "plant_only_amount_million": 2500},
    )
    res = estimate(df, basis(weighting="equal"))
    j = res.journey.set_index("id")
    assert j.loc["a1", "f_owner"] == pytest.approx(1.09)
    assert j.loc["a2", "f_site"] == pytest.approx(1.5)
    assert j.loc["a3", "f_multi"] == pytest.approx(1.15)
    assert j.loc["a4", "f_gas"] == pytest.approx(1 / 1.10)
    assert j.loc["a5", "co2_adj"] == pytest.approx(-95)
    assert j.loc["a6", "f_split"] == pytest.approx(0.5)
    assert j.loc["a3", "u_scoped"] == pytest.approx(500 * 1.15)  # 5000 over 10 MTPA, to one train


def test_brownfield_target_and_graded_gas(tmp_path):
    df = analogs(tmp_path, {})
    bf = estimate(df, basis(site_type="brownfield"))
    assert central_unit(bf) == pytest.approx(1000 / 1.5)
    rich = estimate(df, basis(feed_gas="condensate", gas_method="graded"))
    assert central_unit(rich) == pytest.approx(1310)


# ------------------------------------------------------------- Step 7
def test_size_scaling_on_unit_cost(tmp_path):
    df = analogs(tmp_path, {})
    res = estimate(df, basis(train_size_mtpa=6.0, exponent=0.7))
    assert central_unit(res) == pytest.approx(1000 * (6 / 5) ** (0.7 - 1))


def test_multi_train_target_methods(tmp_path):
    df = analogs(tmp_path, {})
    rev = estimate(df, basis(trains=2))
    assert central_unit(rev) == pytest.approx(1000 / 1.15)
    build = estimate(df, basis(trains=2, multi_train_method="build_up"))
    assert central_unit(build) == pytest.approx(1000 * 0.75)


def test_fitted_exponent_is_reported(tmp_path):
    df = analogs(tmp_path, {"capacity_mtpa": 4.0, "cost_amount_million": 4000 * (4 / 5) ** -0.4},
                 {"capacity_mtpa": 5.0}, {"capacity_mtpa": 6.5, "cost_amount_million": 6500 * (6.5 / 5) ** -0.4})
    res = estimate(df, basis())
    assert res.fitted_exponent["n"] == pytest.approx(0.6, abs=1e-6)
    assert res.exponent == pytest.approx(0.7)


# ------------------------------------------------------------- Step 8
def test_rubric_and_judgment_weights(tmp_path):
    df = analogs(tmp_path, {"region": "Southeast Asia"}, {"cost_amount_million": 6000})
    res = estimate(df, basis(target_region="Southeast Asia"))
    w = res.weights.set_index("id")
    assert w.loc["a1", "rubric_points"] == 5 and w.loc["a1", "suggested_weight"] == 3
    assert w.loc["a2", "rubric_points"] == 4
    res2 = estimate(df, basis(target_region="Southeast Asia", weights={"a2": 1}))
    assert any("reason is required" in x for x in res2.warnings)
    assert central_unit(res2) == pytest.approx((1000 * 3 + 1200 * 1) / 4)


def test_outlier_flag_and_drop(tmp_path):
    df = analogs(tmp_path, {}, {"cost_amount_million": 5100}, {"cost_amount_million": 9000})
    res = estimate(df, basis(weighting="equal"))
    assert res.weights.set_index("id").loc["a3", "outlier"]
    dropped = estimate(df, basis(weighting="equal", drop_reasons={"a3": "Scope unclear"}))
    assert central_unit(dropped) == pytest.approx(1010)


def test_stats_gap_warning(tmp_path):
    df = analogs(tmp_path, {}, {"cost_amount_million": 7000})
    res = estimate(df, basis(weighting="judgment", weights={"a1": 3, "a2": 1},
                             weight_reasons={"a1": "x", "a2": "y"}))
    assert any("second look" in x for x in res.warnings)


# ------------------------------------------------------------- Step 9
def test_site_item_decision_tree(tmp_path):
    df = analogs(tmp_path, {})
    items = [
        SiteItem("Trestle", "marine", True, 0, -200, 300),
        SiteItem("Power", "power", False, 100, 80, 150),
        SiteItem("Small", "other", False, 10, 5, 20),
    ]
    res = estimate(df, basis(site_items=items))
    reg = res.site_register.set_index("item")
    assert reg.loc["Trestle", "base_adder"] == 0 and reg.loc["Trestle", "risk"] == 300
    assert reg.loc["Power", "base_adder"] == 100
    assert reg.loc["Small", "base_adder"] == 0  # 10 is below 1% of 5000
    assert res.central == pytest.approx(5100)


def test_tank_library():
    assert tank_cost(180_000) == pytest.approx(200)
    assert tank_cost(220_000) == pytest.approx(200 * (220 / 180) ** 0.6)


# ------------------------------------------------------------- Step 10
def test_choose_base_rules():
    # A and B have the fewest calls; neither is at an end; A is nearer the middle (5.15).
    ms = [Method("A", 5.1, 1), Method("B", 5.6, 1), Method("C", 6.1, 5), Method("D", 4.9, 2)]
    assert choose_base(ms, "combined")[0].name == "A"
    assert choose_base(ms, "conservative")[0].name == "C"
    assert choose_base(ms, "fewest")[0].name == "A"
    assert choose_base(ms, "middle")[0].name == "A"
    ms2 = [Method("Lo", 4.0, 1), Method("Mid", 5.0, 1), Method("Hi", 6.0, 3)]
    assert choose_base(ms2, "combined")[0].name == "Mid"


def test_brownfield_block_method(tmp_path):
    df = analogs(tmp_path, {})
    b = basis(site_type="brownfield", brownfield_shares=BrownfieldShares(0.5, 0.5, 0.0, 0.0))
    res = estimate(df, b)
    blocks = res.methods.set_index("name")
    # Greenfield 5000: EPC 4500, process 2250, storage/marine 360, utilities 1134, site works 756
    expected = (2250 + 0.5 * 1134 + 0.5 * 756) / 0.9
    assert blocks.loc["Block by block", "value"] == pytest.approx(expected)
    assert blocks.loc["Block by block", "judgment_calls"] == 4


# ------------------------------------------------------------- Step 11
def test_blocks_add_up(tmp_path):
    df = analogs(tmp_path, {})
    res = estimate(df, basis(site_items=[SiteItem("Power", "power", False, 100, 80, 150)]))
    assert res.blocks_by_area["usd_million"].sum() == pytest.approx(res.central)
    assert res.blocks_by_type["share"].sum() == pytest.approx(1.0)


def test_battery_limits_remove_blocks(tmp_path):
    df = analogs(tmp_path, {})
    res = estimate(df, basis(battery_limits=("trains", "utilities", "site_works", "owners_costs")))
    # Storage and marine (8% of EPC = 7.2% of total) removed
    assert res.central == pytest.approx(5000 * (1 - 0.072))


# ------------------------------------------------------------- Step 12
def test_built_range_and_class_warning(tmp_path):
    df = analogs(tmp_path, {})
    res = estimate(df, basis(definition_growth=(0.0, 0.15)))
    assert res.low == pytest.approx(5000)
    assert res.high == pytest.approx(5750)
    assert any("narrower than the class band" in w for w in res.warnings)
    wide = estimate(df, basis(widen_to_class_band=True))
    assert wide.low == pytest.approx(3500) and wide.high == pytest.approx(7500)


def test_contingency_only_for_missing_share(tmp_path):
    df = analogs(tmp_path, {"cost_basis": "epc", "contingency_status": "epc_only"})
    res = estimate(df, basis(apply_owner_costs=False))
    assert res.contingency["applies"]
    assert res.central == pytest.approx(5000 * 1.15)
    df2 = analogs(tmp_path, {})
    assert not estimate(df2, basis()).contingency["applies"]


def test_correlated_comparison(tmp_path):
    df = analogs(tmp_path, {}, {"cost_amount_million": 5500})
    a = estimate(df, basis(weighting="equal"))
    b = estimate(df, basis(weighting="equal", site_type="brownfield", option_name="B"))
    c = compare_options(a, b)
    assert c["central_difference"] == pytest.approx(b.central - a.central)
    assert c["low"] <= c["central_difference"] <= c["high"]
    assert c["high"] < 0  # brownfield is cheaper in every shared case


# ------------------------------------------------------------- Step 13
def test_decision_log_includes_defaults(tmp_path):
    df = analogs(tmp_path, {})
    res = estimate(df, basis(reasons={"step:7": "Practice value"}))
    log = res.log.set_index("switch")
    assert log.loc["Size exponent n", "reason"] == "Practice value"
    assert log.loc["Weighting method", "reason"] == "Default accepted"
    assert (log["date"] != "").all()


def test_preview_types_switch_off_liquefaction_factors():
    df = load_analogs()
    res = estimate(df, make_basis("flng", train_size_mtpa=2.5, site_type="conversion"))
    assert res.journey["f_site"].eq(1).all() and res.journey["f_gas"].eq(1).all()
    assert any("Preview" in w for w in res.warnings)


def test_check_catches_bad_rows(tmp_path):
    df = pd.DataFrame([dict(BASE_ROW, facility_type="spaceport")])
    assert not check_analogs(df).ok
