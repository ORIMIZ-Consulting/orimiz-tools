"""Web form for the FEL1 LNG cost tool.

Run it with:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fel1_lng_cost import FACILITY_TYPES, SCOPES, EstimateBasis, estimate, load_analogues, to_excel_bytes
from fel1_lng_cost.estimate import DEFAULT_EXPONENTS

st.set_page_config(page_title="FEL1 LNG Cost", layout="wide")
st.title("FEL1 LNG cost from analogues")
st.caption(
    "Concept-stage (AACE Class 5) capital cost range for LNG plants, built from "
    "past projects with public costs. A screening tool, not a budget."
)

# ---------- Sidebar: inputs ----------
with st.sidebar:
    st.header("1. Your project")
    ftype = st.selectbox(
        "Facility type", list(FACILITY_TYPES), format_func=FACILITY_TYPES.get
    )
    capacity = st.number_input("Capacity (mtpa of LNG)", min_value=0.1, value=5.0, step=0.5)
    year = st.number_input("Estimate in money of year", 2000, 2100, 2026, step=1)

    st.header("2. Your own analogues (optional)")
    upload = st.file_uploader(
        "CSV with the same columns as the public file",
        type="csv",
        help="Stays in this browser session only. It is not saved or uploaded anywhere.",
    )
    use_public = st.checkbox("Include the public analogue set", value=True)

    st.header("3. Method")
    exponent = st.slider(
        "Size exponent", 0.4, 1.0, DEFAULT_EXPONENTS.get(ftype, 0.7), 0.05,
        help="Cost grows with size to this power. 0.6-0.8 is common for process plants.",
    )
    esc_rate = st.number_input("Escalation per year (%)", -5.0, 20.0, 3.0, 0.5) / 100
    index_file = st.file_uploader(
        "Optional cost index CSV (columns: year, index)", type="csv", key="index",
        help="For example a plant cost index you subscribe to. Replaces the rate for years it covers.",
    )
    scopes = st.multiselect(
        "Analogue scopes to include",
        list(SCOPES),
        default=["plant_only", "plant_plus_pipeline"],
        format_func=SCOPES.get,
    )
    st.subheader("Accuracy band")
    c1, c2 = st.columns(2)
    low = c1.number_input("Low (%)", -50, 0, -30, 5) / 100
    high = c2.number_input("High (%)", 0, 100, 50, 5) / 100
    st.caption("AACE Class 5: low -20% to -50%, high +30% to +100%.")

# ---------- Data ----------
try:
    extra = [upload] if upload is not None else []
    df = load_analogues(*extra, include_public=use_public)
except ValueError as err:
    st.error(str(err))
    st.stop()

cost_index = None
if index_file is not None:
    idx = pd.read_csv(index_file)
    cost_index = {int(y): float(v) for y, v in zip(idx.iloc[:, 0], idx.iloc[:, 1])}

pool = df[df["facility_type"] == ftype]

# ---------- Location ----------
st.subheader("Location")
st.write(
    "Set a factor for each region on any common base (for example US Gulf Coast = 1.00). "
    "The tool divides out the analogue's factor and applies yours. Leave all at 1.00 "
    "to make no location adjustment."
)
regions = sorted(pool["region"].unique())
loc_col, tgt_col = st.columns([2, 1])
with loc_col:
    loc_table = st.data_editor(
        pd.DataFrame({"region": regions, "factor": [1.0] * len(regions)}),
        disabled=["region"], hide_index=True, width="stretch",
    )
with tgt_col:
    target_region = st.text_input("Target location", "Target site")
    target_factor = st.number_input("Target location factor", 0.3, 3.0, 1.0, 0.05)
region_factors = dict(zip(loc_table["region"], loc_table["factor"]))

# ---------- Analogue choice ----------
st.subheader("Analogues")
st.write("Untick any project you do not want to use.")
view = pool[pool["scope"].isin(scopes)][
    ["id", "project", "country", "site_type", "scope", "capacity_mtpa",
     "cost_usd_million", "cost_year", "unit_cost_usd_per_tpa", "notes"]
].copy()
view.insert(0, "use", True)
chosen = st.data_editor(
    view, hide_index=True, width="stretch",
    disabled=[c for c in view.columns if c != "use"],
    column_config={
        "cost_usd_million": st.column_config.NumberColumn("Cost (USD m)", format="%d"),
        "unit_cost_usd_per_tpa": st.column_config.NumberColumn("USD per tpa", format="%d"),
        "capacity_mtpa": st.column_config.NumberColumn("mtpa"),
    },
)
excluded = tuple(chosen.loc[~chosen["use"], "id"])

basis = EstimateBasis(
    facility_type=ftype,
    capacity_mtpa=float(capacity),
    estimate_year=int(year),
    target_region=target_region,
    target_location_factor=float(target_factor),
    region_location_factors=region_factors,
    escalation_rate=float(esc_rate),
    cost_index=cost_index,
    scale_exponent=float(exponent),
    scopes=tuple(scopes),
    exclude_ids=excluded,
    class_low=float(low),
    class_high=float(high),
)

try:
    result = estimate(df, basis)
except ValueError as err:
    st.warning(str(err))
    st.stop()

# ---------- Results ----------
st.subheader(f"Result in {int(year)} US dollars")
m1, m2, m3, m4 = st.columns(4)
m1.metric("P10", f"${result.p10_usd_million:,.0f} m")
m2.metric("P50", f"${result.p50_usd_million:,.0f} m")
m3.metric("P90", f"${result.p90_usd_million:,.0f} m")
m4.metric("P50 unit cost", f"${result.p50_unit_cost_usd_per_tpa:,.0f} per tpa")
for w in result.warnings:
    st.info(w)

a = result.analogues.sort_values("estimate_usd_million")
fig = go.Figure(go.Bar(
    x=a["estimate_usd_million"], y=a["project"], orientation="h",
    marker_opacity=0.35 + 0.65 * a["weight"],
    hovertemplate="%{y}<br>%{x:,.0f} USD m<extra></extra>",
))
for value, label in [(result.p10_usd_million, "P10"), (result.p50_usd_million, "P50"),
                     (result.p90_usd_million, "P90")]:
    fig.add_vline(x=value, line_dash="dot" if label != "P50" else "solid",
                  annotation_text=label, annotation_position="top")
fig.update_layout(
    height=max(260, 40 * len(a) + 80), margin=dict(l=10, r=10, t=30, b=10),
    xaxis_title="Estimate for your project (USD million)", yaxis_title=None,
)
st.plotly_chart(fig, width="stretch")
st.caption("Each bar is one analogue moved to your size, year and location. Darker bars carry more weight.")

with st.expander("Step-by-step numbers for each analogue"):
    st.dataframe(
        result.analogues[[
            "project", "capacity_mtpa", "cost_year", "cost_usd_million", "escalation_factor",
            "location_adjustment", "size_factor", "estimate_usd_million", "weight_share", "source_url",
        ]].round(3),
        hide_index=True, width="stretch",
        column_config={"source_url": st.column_config.LinkColumn("Source")},
    )

st.download_button(
    "Download Excel workbook",
    data=to_excel_bytes(result),
    file_name=f"fel1_{ftype}_{capacity:g}mtpa_{int(year)}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
