"""Web app for the FEL1 LNG Cost tool.

Run it with:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from fel1_lng_cost import (
    BrownfieldShares,
    Method,
    SiteItem,
    compare_options,
    dredging_cost,
    estimate,
    load_analogs,
    make_basis,
    tank_cost,
    to_excel_bytes,
)
from fel1_lng_cost import charts
from fel1_lng_cost import factors as F

st.set_page_config(page_title="FEL1 LNG Cost", layout="wide")
st.title("FEL1 LNG cost from analogs")
st.caption(
    "Concept-stage (AACE Class 5) capital cost for LNG plants from public analog projects, "
    "following the FEL 1 LNG Capital Cost Estimating Guideline v0.1. Every method choice is a "
    "switch, and every switch goes into the decision log."
)
W = "stretch"


def reason_box(step: int, key: str) -> str:
    return st.text_input(f"Reason for the Step {step} choices (goes into the decision log)", key=key)


# ================================================================ Step 1 (sidebar)
with st.sidebar:
    st.header("Step 1. Key inputs")
    purpose = st.selectbox("Purpose", list(F.PURPOSES), format_func=F.PURPOSES.get,
                           help="Sets the effort the rest deserves. Gate 1 asks you to review every switch.")
    ftype = st.selectbox("Facility type", list(F.FACILITY_TYPES), format_func=F.FACILITY_TYPES.get)
    D = make_basis(ftype)
    c1, c2 = st.columns(2)
    train = c1.number_input("MTPA per train", 0.1, 15.0, 5.0, 0.1)
    trains = c2.number_input("Trains", 1, 12, 1, 1)
    site_type = st.selectbox("Site type", list(F.SITE_TYPES[ftype]), format_func=F.SITE_TYPES[ftype].get)
    location_name = st.text_input("Location", "Target site")
    groups = list(F.LOCATION_GROUPS)
    group = st.selectbox("Nearest OIES location group", groups, index=groups.index(D.location_group),
                         format_func=lambda g: f"{F.LOCATION_GROUPS[g][1]} ({F.LOCATION_GROUPS[g][0]:.2f})")
    steps = st.slider("Steps of 0.10", -3, 3, 0,
                      help="One step down for an established industrial LNG site with a trained "
                           "workforce; one step up for a first-of-its-kind remote site.")
    override = st.checkbox("Enter my own location factor")
    loc_factor = st.number_input("Location factor", 0.5, 3.0, 1.0, 0.05) if override else None
    est_year = st.number_input("Estimate year", 2000, 2100, 2026, 1)
    c1, c2 = st.columns(2)
    currency = c1.text_input("Report currency", "USD")
    fx = c2.number_input("Units per USD", 0.0001, 100000.0, 1.0)
    st.subheader("Optional")
    feed = st.selectbox("Feed gas", list(F.FEED_GAS), format_func=F.FEED_GAS.get)
    co2 = st.checkbox("CO2 removal and sequestration at target")
    family = st.selectbox("Process family", [k for k in F.PROCESS_FAMILIES if k != "not_stated"],
                          format_func=F.PROCESS_FAMILIES.get)
    limits = st.multiselect("Battery limits", list(F.BATTERY_LIMIT_ITEMS),
                            default=list(F.DEFAULT_BATTERY_LIMITS), format_func=F.BATTERY_LIMIT_ITEMS.get)
    c1, c2 = st.columns(2)
    class_low = c1.number_input("Accuracy low %", -50, 0, -30, 5) / 100
    class_high = c2.number_input("Accuracy high %", 0, 100, 50, 5) / 100
    reason1 = st.text_input("Reason for Step 1 choices")

tab_res, tab_an, tab_sw, tab_site, tab_opt, tab_log = st.tabs(
    ["Result", "Analogs and weights", "Method switches", "Site items", "Options and variants", "Decision log"]
)
reasons: dict[str, str] = {"step:1": reason1} if reason1 else {}

# ================================================================ Method switches
with tab_sw:
    st.write("Each switch shows its default. Change it only with a reason.")
    k = ftype  # widget keys reset when the facility type changes
    with st.expander("Step 2. Analog selection", expanded=False):
        use_band = st.checkbox("Filter on train size", D.train_band is not None, key=f"band_on{k}")
        band = st.slider("Train size band (times target)", 0.2, 5.0, D.train_band or (0.5, 2.0), 0.1,
                         key=f"band{k}") if use_band else None
        use_fid = st.checkbox("Filter on FID date", D.fid_window_years is not None, key=f"fid_on{k}")
        fid_window = st.number_input("FID within (years)", 1, 40, D.fid_window_years or 15,
                                     key=f"fid{k}") if use_fid else None
        scopes = st.multiselect("Scopes accepted", list(F.SCOPES), default=list(D.scopes),
                                format_func=F.SCOPES.get, key=f"scopes{k}")
        splits = st.checkbox("Also use analogs of other scopes where a plant-only split exists (OIES)",
                             D.use_plant_splits, key=f"splits{k}")
        sites_ok = st.multiselect("Site types accepted (empty = all)", list(F.SITE_TYPES[ftype]),
                                  default=list(D.site_types_allowed or ()) if ftype != "flng" else [site_type],
                                  key=f"sites{k}{site_type}")
        cluster = st.checkbox("Separate cluster for trains below 1 or above 6 MTPA", D.cluster_rule, key=f"cl{k}")
        fam_filter = st.checkbox("Same process family only", D.process_family_filter, key=f"fam{k}")
        c1, c2 = st.columns(2)
        min_warn = c1.number_input("Warn below", 1, 20, D.min_count_warn, key=f"mw{k}")
        min_stop = c2.number_input("Stop below", 1, 20, D.min_count_stop, key=f"ms{k}")
        r = reason_box(2, f"r2{k}")
        if r:
            reasons["step:2"] = r
    with st.expander("Step 3. Adjustment method"):
        adj = st.radio("Method", ["multiply", "hybrid"], horizontal=True, key=f"adj{k}",
                       format_func={"multiply": "A. Multiply (default)",
                                    "hybrid": "C. Hybrid: add storage and marine as blocks"}.get)
        hyb = st.number_input("Hybrid: storage and marine share removed from analogs", 0.0, 0.5,
                              D.hybrid_step_share, 0.01, key=f"hyb{k}") if adj == "hybrid" else D.hybrid_step_share
        if adj == "hybrid":
            st.caption("Enter the target's own tanks and marine works as Step 9 site items with "
                       "category storage or marine. They are added to the base as blocks.")
        r = reason_box(3, f"r3{k}")
        if r:
            reasons["step:3"] = r
    with st.expander("Step 4. Escalation"):
        idx_file = st.file_uploader("Cost index CSV (columns: year, index)", type="csv", key=f"idx{k}",
                                    help="CEPCI or an upstream capital cost index. Copyrighted indices "
                                         "cannot ship with the tool; load your own values.")
        idx_name = st.text_input("Index name", D.index_name, key=f"idxn{k}")
        modes = ["auto", "constant", "index", "damped", "two_cases"]
        mode = st.selectbox("Method", modes, key=f"esc{k}", format_func={
            "auto": "Default: two cases if an index is loaded, else constant rate",
            "constant": "A. Constant rate", "index": "B/C. Cost index", "damped": "D. Damped index",
            "two_cases": "E. Two cases of my choice"}.get)
        c1, c2, c3 = st.columns(3)
        rate = c1.number_input("Rate % per year", -5.0, 20.0, D.escalation_rate * 100, 0.5, key=f"rate{k}") / 100
        rate_low = c2.number_input("Low rate % (two cases)", -5.0, 20.0, D.escalation_rate_low * 100, 0.5,
                                   key=f"ratel{k}") / 100
        damp = c3.number_input("Damping fraction f", 0.0, 1.5, D.damping_f, 0.05, key=f"damp{k}")
        case_opts = ["index", "damped", "constant", "constant_low"]
        c1, c2 = st.columns(2)
        hi_case = c1.selectbox("High case", case_opts, 0, key=f"hic{k}")
        lo_case = c2.selectbox("Low case", case_opts, 1, key=f"loc{k}")
        r = reason_box(4, f"r4{k}")
        if r:
            reasons["step:4"] = r
    cost_index = None
    if idx_file is not None:
        idx = pd.read_csv(idx_file).dropna()
        cost_index = {int(y): float(v) for y, v in zip(idx.iloc[:, 0], idx.iloc[:, 1])}
    with st.expander("Step 5. Location"):
        loc_method = st.radio("Method", ["full", "construction_share"], horizontal=True, key=f"lm{k}",
                              format_func={"full": "A/B. Whole factor (default)",
                                           "construction_share": "C. Only on the construction share"}.get)
        share = st.number_input("Construction share", 0.05, 1.0, D.construction_share, 0.01, key=f"cs{k}")
        gtable = st.data_editor(
            pd.DataFrame({"group": list(D.location_groups), "factor": list(D.location_groups.values())}),
            disabled=["group"], hide_index=True, key=f"gt{k}", width=W)
        r = reason_box(5, f"r5{k}")
        if r:
            reasons["step:5"] = r
    with st.expander("Step 6. Scope and complexity"):
        liq = ftype == F.LIQUEFACTION
        if not liq:
            st.info("Preview type: site, multi-train, gas and CO2 factors do not apply.")
        c1, c2 = st.columns(2)
        own_on = c1.checkbox("Owner's costs on EPC-only figures", D.apply_owner_costs, key=f"own{k}")
        own_f = c2.number_input("Owner's cost factor", 1.0, 1.3, D.owner_cost_factor, 0.01, key=f"ownf{k}")
        site_on = st.checkbox("Site type adjustment", D.apply_site_factor, key=f"sf{k}", disabled=not liq)
        stable = st.data_editor(
            pd.DataFrame({"site_type": list(D.site_factors), "factor_to_greenfield": list(D.site_factors.values())}),
            disabled=["site_type"], hide_index=True, key=f"st{k}", width=W)
        c1, c2 = st.columns(2)
        multi_on = c1.checkbox("Multi-train analog to one train", D.apply_multi_train, key=f"mt{k}", disabled=not liq)
        multi_f = c2.number_input("Multi-train factor", 1.0, 1.4, D.multi_train_factor, 0.01, key=f"mtf{k}")
        gas = st.radio("Gas complexity", ["simple", "graded", "off"], horizontal=True, key=f"gas{k}",
                       index=["simple", "graded", "off"].index(D.gas_method), disabled=not liq,
                       format_func={"simple": "A. Rich x1.10 (default)",
                                    "graded": "B. Graded LPG 1.14 / condensate 1.31 / sulphur 1.52",
                                    "off": "Off"}.get)
        co2_rm = st.checkbox("Remove CO2 sequestration from analogs (USD 95 per tpa)",
                             D.apply_co2_removal, key=f"co2{k}", disabled=not liq)
        r = reason_box(6, f"r6{k}")
        if r:
            reasons["step:6"] = r
    with st.expander("Step 7. Size scaling"):
        c1, c2 = st.columns(2)
        n = c1.number_input("Exponent n", 0.3, 1.2, D.resolved_exponent(), 0.05, key=f"n{k}")
        fitted = c2.checkbox("Use the fitted exponent instead", False, key=f"fit{k}")
        extrap = st.number_input("Extrapolation warning limit", 1.0, 5.0, D.extrapolation_limit, 0.1, key=f"ex{k}")
        mt_method = st.selectbox("Multi-train target", ["reverse_factor", "build_up", "plant_capacity"],
                                 key=f"mtm{k}", format_func={
                                     "reverse_factor": "A. Reverse the one-train factor (default)",
                                     "build_up": "B. Build up by train (phased)",
                                     "plant_capacity": "C. Scale on plant capacity (comparison only)"}.get)
        repeat = st.number_input("Repeat train factor (build-up)", 0.2, 1.0, D.repeat_train_factor, 0.05, key=f"rep{k}")
        r = reason_box(7, f"r7{k}")
        if r:
            reasons["step:7"] = r
    with st.expander("Step 12. Range"):
        rmethod = st.selectbox("Range method", ["built", "class_band", "analog_spread"], key=f"rm{k}",
                               format_func={"built": "C. Built from named uncertainties (default)",
                                            "class_band": "A. Class band", "analog_spread": "B. Analog spread"}.get)
        c1, c2, c3 = st.columns(3)
        g_lo = c1.number_input("Definition growth low %", -20, 30, 0, 1, key=f"gl{k}") / 100
        g_hi = c2.number_input("Definition growth high %", 0, 60, 15, 1, key=f"gh{k}") / 100
        cont = c3.number_input("Contingency % (non-budget share)", 0, 50, int(D.contingency_rate * 100), 1,
                               key=f"ct{k}") / 100
        widen = st.checkbox("Widen to the class band when the built range is narrower", False, key=f"wd{k}")
        r = reason_box(12, f"r12{k}")
        if r:
            reasons["step:12"] = r

# ================================================================ Site items
with tab_site:
    st.write(
        "Step 9 rule: the normalized analog level is the base. A site item travels as a risk or "
        "opportunity when the analogs already carry it in a typical form. If they do not, it is "
        "added to the base when material. USD million, estimate-year money."
    )
    materiality = st.number_input("Materiality threshold (% of base)", 0.1, 10.0, D.materiality * 100, 0.1) / 100
    empty = pd.DataFrame({
        "name": pd.Series(dtype=str), "category": pd.Series(dtype=str),
        "analogs_carry_typical": pd.Series(dtype=bool), "central": pd.Series(dtype=float),
        "low": pd.Series(dtype=float), "high": pd.Series(dtype=float),
        "driver": pd.Series(dtype=str), "status": pd.Series(dtype=str), "source": pd.Series(dtype=str),
    })
    items_df = st.data_editor(
        empty, num_rows="dynamic", key="items", width=W,
        column_config={
            "category": st.column_config.SelectboxColumn(options=list(F.SITE_ITEM_CATEGORIES)),
            "analogs_carry_typical": st.column_config.CheckboxColumn("Analogs carry it?", default=True),
            "central": st.column_config.NumberColumn(default=0.0),
            "low": st.column_config.NumberColumn(default=0.0),
            "high": st.column_config.NumberColumn(default=0.0),
            "status": st.column_config.SelectboxColumn(options=["open", "closed"], default="open"),
        },
    )
    st.subheader("Item library helpers")
    c1, c2 = st.columns(2)
    with c1:
        vol = st.number_input("Tank size (m3)", 10_000, 300_000, 180_000, 10_000)
        cnt = st.number_input("Tank count", 1, 6, 1)
        st.caption(
            f"About USD {tank_cost(vol, cnt):,.0f}m in {F.TANK_REFERENCE['year']} money "
            f"(USD {F.TANK_REFERENCE['cost_musd']:.0f}m per 180,000 m3, exponent 0.6; "
            f"{F.TANK_REFERENCE['source']}). Norm: one tank per 4 to 5 MTPA train."
        )
    with c2:
        dvol = st.number_input("Dredging volume (m3)", 0, 50_000_000, 1_000_000, 100_000)
        dlo, dhi = dredging_cost(dvol)
        st.caption(f"About USD {dlo:,.0f}m to {dhi:,.0f}m at USD 15 to 30 per m3 (Cuyutlan, Soyo). "
                   "PNG LNG 2.4 km jetty: about USD 258m (2010).")

site_items = []
for row in items_df.dropna(subset=["name"]).itertuples():
    if not str(row.name).strip():
        continue
    site_items.append(SiteItem(
        name=str(row.name), category=row.category or "other",
        analogs_carry_typical=bool(row.analogs_carry_typical) if pd.notna(row.analogs_carry_typical) else True,
        central=float(row.central or 0), low=float(row.low or 0), high=float(row.high or 0),
        driver=str(row.driver or ""), status=str(row.status or "open"), source=str(row.source or ""),
    ))

# ================================================================ Options and variants
with tab_opt:
    st.subheader("Step 10. Other methods for this option")
    st.write("Add each other way you have priced this option, with its number of judgment calls on "
             "top of the shared inputs. The guideline asks for at least two independent methods.")
    meth_df = st.data_editor(
        pd.DataFrame({"name": pd.Series(dtype=str), "value_usd_million": pd.Series(dtype=float),
                      "judgment_calls": pd.Series(dtype=int), "note": pd.Series(dtype=str)}),
        num_rows="dynamic", key="methods", width=W)
    c1, c2 = st.columns(2)
    analog_calls = c1.number_input("Judgment calls in the analog method", 0, 10, 1)
    rule = c2.selectbox("Rule for the base", ["combined", "fewest", "middle", "conservative"], format_func={
        "combined": "D. Fewest calls, not at either end (default)", "fewest": "A. Fewest judgment calls",
        "middle": "B. Middle of the spread", "conservative": "C. Most conservative"}.get)
    gap_note = st.text_area("Why the methods differ")
    shares = None
    if ftype == F.LIQUEFACTION and site_type != "greenfield":
        if st.checkbox("Add the block-by-block brownfield method"):
            c1, c2, c3, c4 = st.columns(4)
            shares = BrownfieldShares(
                utilities=c1.number_input("Utilities to build", 0.0, 1.0, 0.5, 0.05),
                site_works=c2.number_input("Site works to build", 0.0, 1.0, 0.3, 0.05),
                storage_marine=c3.number_input("Storage and marine to build", 0.0, 1.0, 0.0, 0.05),
                tie_ins_musd=c4.number_input("Tie-ins (USD m)", 0.0, 5000.0, 0.0, 10.0),
            )
            st.caption("Each share is the part of that greenfield block the existing site does not provide.")
    st.subheader("Compare with a second option")
    compare = st.checkbox("Add Option B (shares escalation, location factors and the analog level)")
    if compare:
        c1, c2, c3 = st.columns(3)
        b_name = c1.text_input("Option B name", "Option B")
        b_site = c2.selectbox("Option B site type", list(F.SITE_TYPES[ftype]),
                              format_func=F.SITE_TYPES[ftype].get, key="bsite")
        b_trains = c3.number_input("Option B trains", 1, 12, int(trains))
        c1, c2, c3 = st.columns(3)
        b_train = c1.number_input("Option B MTPA per train", 0.1, 15.0, float(train), 0.1)
        b_steps = c2.slider("Option B location steps", -3, 3, int(steps))
        b_items = c3.checkbox("Option B uses the same site items", True)

methods = [Method(str(m.name), float(m.value_usd_million), int(m.judgment_calls or 0), str(m.note or ""))
           for m in meth_df.dropna(subset=["name", "value_usd_million"]).itertuples()]

# ================================================================ Analogs and weights
with tab_an:
    st.subheader("Analog data")
    c1, c2 = st.columns([3, 1])
    upload = c1.file_uploader("Your own analogs (CSV, same columns as data/analog_template.csv)", type="csv",
                              help="Stays in this browser session. It is not saved or uploaded anywhere.")
    use_public = c2.checkbox("Include the public set", True)
    st.subheader("Step 8. Combining")
    c1, c2 = st.columns(2)
    weighting = c1.selectbox("Weighting", ["judgment", "rubric", "size", "equal"], format_func={
        "judgment": "D. Judgment prompted by the rubric (default)", "rubric": "C. Rubric only",
        "size": "B. Size similarity", "equal": "A. Equal"}.get)
    outlier = c2.number_input("Outlier flag (% from median)", 5, 100, 30, 5) / 100
    r8 = st.text_input("Reason for the Step 8 choices")
    if r8:
        reasons["step:8"] = r8

try:
    df = load_analogs(*([upload] if upload is not None else []), include_public=use_public)
except ValueError as err:
    st.error(str(err))
    st.stop()

common = dict(
    purpose=purpose, train_size_mtpa=float(train), trains=int(trains), site_type=site_type,
    location_name=location_name, location_group=group, location_steps=int(steps), location_factor=loc_factor,
    estimate_year=int(est_year), report_currency=currency, report_fx=float(fx), feed_gas=feed,
    co2_sequestration=co2, process_family=family, battery_limits=tuple(limits),
    class_low=float(class_low), class_high=float(class_high),
    train_band=tuple(band) if band else None, fid_window_years=int(fid_window) if fid_window else None,
    scopes=tuple(scopes), use_plant_splits=splits, site_types_allowed=tuple(sites_ok) or None,
    cluster_rule=cluster, process_family_filter=fam_filter, min_count_warn=int(min_warn),
    min_count_stop=int(min_stop), adjustment_method=adj, hybrid_step_share=float(hyb),
    escalation_mode=mode, escalation_rate=float(rate), escalation_rate_low=float(rate_low),
    cost_index=cost_index, index_name=idx_name, damping_f=float(damp), two_case_high=hi_case,
    two_case_low=lo_case, location_method=loc_method, construction_share=float(share),
    location_groups=dict(zip(gtable["group"], gtable["factor"])), apply_owner_costs=own_on,
    owner_cost_factor=float(own_f), apply_site_factor=site_on,
    site_factors=dict(zip(stable["site_type"], stable["factor_to_greenfield"])),
    apply_multi_train=multi_on, multi_train_factor=float(multi_f), gas_method=gas if liq else "off",
    apply_co2_removal=co2_rm, exponent=float(n), use_fitted_exponent=fitted,
    extrapolation_limit=float(extrap), multi_train_method=mt_method, repeat_train_factor=float(repeat),
    weighting=weighting, outlier_threshold=float(outlier), materiality=float(materiality),
    range_method=rmethod, definition_growth=(float(g_lo), float(g_hi)), contingency_rate=float(cont),
    widen_to_class_band=widen,
)
basis = make_basis(ftype, **common, site_items=site_items, methods=methods,
                   analog_method_judgment_calls=int(analog_calls), base_rule=rule,
                   brownfield_shares=shares, method_gap_note=gap_note, reasons=reasons,
                   option_name="Option A")

# A first run gives the rubric, so the weights editor can show it.
with tab_an:
    regions = [""] + sorted(df.loc[df["facility_type"] == ftype, "region"].unique())
    st.selectbox("Target region (for the rubric's first criterion)", regions, key="target_region",
                 format_func=lambda x: x or "(not set)")
    basis = basis.with_changes(target_region=st.session_state.get("target_region", ""))
    try:
        pre = estimate(df, basis)
    except ValueError as err:
        st.error(str(err))
        st.stop()
    st.write("Set your weight (1, 2 or 3) for each analog. A reason is required where it differs "
             "from the rubric. Tick drop for any outlier you remove, with a reason.")
    wt = pre.weights[["id", "project", "rubric_points", "suggested_weight", "value", "vs_median", "outlier"]].copy()
    wt["your_weight"] = wt["suggested_weight"]
    wt["reason"] = ""
    wt["drop"] = False
    wt["drop_reason"] = ""
    editor_key = "w_" + str(abs(hash(tuple(wt["id"]))))
    edited = st.data_editor(
        wt, key=editor_key, hide_index=True, width=W,
        disabled=["id", "project", "rubric_points", "suggested_weight", "value", "vs_median", "outlier"],
        column_config={
            "id": None,
            "project": st.column_config.TextColumn("Project"),
            "rubric_points": st.column_config.NumberColumn("Rubric points (of 5)"),
            "suggested_weight": st.column_config.NumberColumn("Rubric weight"),
            "value": st.column_config.NumberColumn("USD/tpa after Step 7", format="%d"),
            "vs_median": st.column_config.NumberColumn("vs median", format="percent"),
            "outlier": st.column_config.CheckboxColumn("Outlier"),
            "your_weight": st.column_config.SelectboxColumn("Your weight", options=[1, 2, 3]),
            "reason": st.column_config.TextColumn("Reason"),
            "drop": st.column_config.CheckboxColumn("Drop"),
            "drop_reason": st.column_config.TextColumn("Drop reason"),
        },
    )
    rejected = pre.pool[~pre.pool["selected"]][["project", "selection_note", "train_size_mtpa", "fid_year", "scope"]]
    with st.expander(f"Analogs filtered out in Step 2 ({len(rejected)})"):
        st.dataframe(rejected, hide_index=True, width=W)

weights = {r.id: int(r.your_weight) for r in edited.itertuples() if int(r.your_weight) != int(r.suggested_weight)}
w_reasons = {r.id: r.reason for r in edited.itertuples() if str(r.reason).strip()}
drops = {r.id: (r.drop_reason or "No reason given") for r in edited.itertuples() if r.drop}
basis = basis.with_changes(weights=weights, weight_reasons=w_reasons, drop_reasons=drops)

try:
    res = estimate(df, basis)
except ValueError as err:
    with tab_res:
        st.error(str(err))
    st.stop()

comparison = None
res_b = None
if compare:
    try:
        b_basis = basis.with_changes(
            option_name=b_name, site_type=b_site, trains=int(b_trains), train_size_mtpa=float(b_train),
            location_steps=int(b_steps), site_items=site_items if b_items else [], methods=[],
            brownfield_shares=None, weights={}, weight_reasons={}, drop_reasons={},
            site_types_allowed=(b_site,) if ftype == "flng" else basis.site_types_allowed)
        res_b = estimate(df, b_basis)
        comparison = compare_options(res, res_b)
    except ValueError as err:
        with tab_opt:
            st.error(f"Option B: {err}")

# ================================================================ Result
with tab_res:
    fxv = basis.report_fx
    cur = basis.report_currency
    st.subheader(f"{basis.trains} x {basis.train_size_mtpa:g} MTPA, {location_name}, money of {basis.estimate_year}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Low", f"{res.low * fxv:,.0f} {cur} m", f"{res.low / res.central - 1:+.0%}", delta_color="off")
    m2.metric("Base", f"{res.central * fxv:,.0f} {cur} m")
    m3.metric("High", f"{res.high * fxv:,.0f} {cur} m", f"{res.high / res.central - 1:+.0%}", delta_color="off")
    m4.metric("Unit cost", f"{res.unit_cost:,.0f} USD/tpa")
    st.caption(f"AACE Class 5. Base method: {res.base_method}. {res.base_reason} "
               "The range is a set of reasoned bounds, not a statistical P10 and P90.")
    for w in res.warnings:
        st.warning(w)

    st.plotly_chart(charts.range_chart([res] + ([res_b] if res_b else []), comparison), width=W)
    if comparison:
        st.write(
            f"**{comparison['option_b']} minus {comparison['option_a']}:** "
            f"{comparison['central_difference']:,.0f} USD m (correlated range {comparison['low']:,.0f} "
            f"to {comparison['high']:,.0f}). {comparison['note']}"
        )

    st.subheader("Weights panel")
    s = res.stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Weighted mean", f"{s['weighted_mean']:,.0f} USD/tpa")
    c2.metric("Simple mean", f"{s['simple_mean']:,.0f}")
    c3.metric("Median", f"{s['median']:,.0f}")
    c4.metric("Analogs used", s["count"])

    cases = list(res.journey["case"].unique())
    case = st.radio("Escalation case for the journey", cases, horizontal=True) if len(cases) > 1 else cases[0]
    st.plotly_chart(charts.journey_chart(res, case), width=W)
    with st.expander("Analog journey table"):
        st.dataframe(res.journey[res.journey["case"] == case].round(3), hide_index=True, width=W)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.size_chart(res), width=W)
    fe = res.fitted_exponent
    c1.caption(f"Fitted n = {fe['n']:.2f} (R2 = {fe['r2']:.2f}, {fe['count']} analogs). Shown only; "
               "the guideline takes n from practice.")
    esc_fig = charts.escalation_chart(res)
    if esc_fig:
        c2.plotly_chart(esc_fig, width=W)
    if len(res.calibration):
        c2.write("Damping calibration pairs (Step 4):")
        c2.dataframe(res.calibration.round(3), hide_index=True, width=W)

    st.subheader("Cost blocks")
    c1, c2 = st.columns(2)
    c1.dataframe(res.blocks_by_area.round(3), hide_index=True, width=W)
    c2.dataframe(res.blocks_by_type.round(3), hide_index=True, width=W)

    st.subheader("Risk and opportunity register")
    st.dataframe(res.site_register, hide_index=True, width=W)

    st.subheader("Sensitivities")
    st.dataframe(res.sensitivities.round(3), hide_index=True, width=W,
                 column_config={"change": st.column_config.NumberColumn(format="percent")})
    st.dataframe(res.methods, hide_index=True, width=W)

    with st.expander("References"):
        st.dataframe(res.references, hide_index=True, width=W,
                     column_config={"source": st.column_config.LinkColumn()})
    st.download_button(
        "Download Excel workbook", data=to_excel_bytes(res, comparison),
        file_name=f"fel1_{ftype}_{basis.trains}x{basis.train_size_mtpa:g}_{basis.estimate_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with tab_log:
    st.write("Every switch, defaults included: setting, default, reason and date.")
    st.dataframe(res.log, hide_index=True, width=W)
