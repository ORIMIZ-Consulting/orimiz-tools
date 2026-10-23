"""Plotly charts for the Step 13 outputs."""
from __future__ import annotations

import plotly.graph_objects as go

from .estimate import EstimateResult
from .export import JOURNEY_STEPS, size_curve

INK = "#1F3A5F"


def _layout(fig: go.Figure, height: int, **kw) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=-0.15), **kw)
    return fig


def journey_chart(r: EstimateResult, case: str | None = None) -> go.Figure:
    case = case or r.journey["case"].iloc[0]
    j = r.journey[r.journey["case"] == case].merge(r.weights[["id", "dropped"]], on="id")
    steps = [label for _, label in JOURNEY_STEPS]
    fig = go.Figure()
    for _, a in j.iterrows():
        fig.add_trace(go.Scatter(
            x=steps, y=[a[k] for k, _ in JOURNEY_STEPS], mode="lines+markers", name=a["project"],
            line=dict(dash="dot" if a["dropped"] else "solid"),
            hovertemplate="%{x}: %{y:,.0f} USD/tpa<extra>" + a["project"] + "</extra>",
        ))
    fig.add_hline(y=r.stats["weighted_mean"], line_color=INK, line_width=2,
                  annotation_text="Weighted mean", annotation_position="top left")
    return _layout(fig, 480, title=f"Analog journey ({case} escalation case)", yaxis_title="USD per tpa")


def escalation_chart(r: EstimateResult) -> go.Figure | None:
    if r.journey["case"].nunique() < 2:
        return None
    p = r.journey.pivot_table(index="project", columns="case", values="u_final").reset_index()
    fig = go.Figure()
    for case in [c for c in p.columns if c != "project"]:
        fig.add_trace(go.Bar(y=p["project"], x=p[case], name=case, orientation="h"))
    return _layout(fig, max(300, 28 * len(p) + 100), barmode="group",
                   title="Escalation cases per analog", xaxis_title="USD per tpa")


def size_chart(r: EstimateResult) -> go.Figure:
    first = r.journey["case"].iloc[0]
    j = r.journey[r.journey["case"] == first].merge(r.pool[["id", "train_size_mtpa"]], on="id")
    j = j.merge(r.weights[["id", "weight_share"]], on="id")
    curve = size_curve(r)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=j["train_size_mtpa"], y=j["u_scoped"], mode="markers", name="Analogs (Step 6 value)",
        marker=dict(size=8 + 30 * j["weight_share"], opacity=0.75),
        text=j["project"], hovertemplate="%{text}<br>%{x:.2f} MTPA, %{y:,.0f} USD/tpa<extra></extra>",
    ))
    fig.add_trace(go.Scatter(x=curve["train_size_mtpa"], y=curve["curve_usd_per_tpa"], mode="lines",
                             name=f"Curve, n = {r.exponent:.2f}", line=dict(color=INK)))
    t0 = r.basis.train_size_mtpa
    u0 = float(curve.iloc[(curve["train_size_mtpa"] - t0).abs().argmin()]["curve_usd_per_tpa"])
    fig.add_trace(go.Scatter(x=[t0], y=[u0], mode="markers", name="Target train",
                             marker=dict(symbol="star", size=16, color="#C0392B")))
    return _layout(fig, 420, title="Size curve (one-train basis)", xaxis_title="Train size (MTPA)",
                   yaxis_title="USD per tpa")


def range_chart(results: list[EstimateResult], comparison: dict | None = None) -> go.Figure:
    names = [r.basis.option_name for r in results]
    lows = [r.low for r in results]
    bases = [r.central for r in results]
    highs = [r.high for r in results]
    if comparison:
        names.append(f"Difference ({comparison['option_b']} - {comparison['option_a']})")
        lows.append(comparison["low"])
        bases.append(comparison["central_difference"])
        highs.append(comparison["high"])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names, x=[h - lo for h, lo in zip(highs, lows)], base=lows, orientation="h",
        marker_color="rgba(31,58,95,0.25)", name="Low to high",
        hovertemplate="%{y}<br>Low %{base:,.0f} to high %{x:,.0f} wide<extra></extra>",
    ))
    fig.add_trace(go.Scatter(y=names, x=bases, mode="markers+text", name="Base",
                             text=[f"{v:,.0f}" for v in bases], textposition="top center",
                             marker=dict(color=INK, size=14, symbol="line-ns-open", line_width=3)))
    for label, xs, pos in (("Low", lows, "middle left"), ("High", highs, "middle right")):
        fig.add_trace(go.Scatter(y=names, x=xs, mode="text", text=[f"{v:,.0f}" for v in xs],
                                 textposition=pos, showlegend=False, hoverinfo="skip"))
    pad = 0.12 * (max(highs) - min(lows) or 1)
    fig.update_xaxes(range=[min(lows) - pad, max(highs) + pad])
    return _layout(fig, 160 + 70 * len(names), title="Range (USD million)", xaxis_title="USD million")


def blocks_chart(r: EstimateResult) -> go.Figure:
    a = r.blocks_by_area[r.blocks_by_area["usd_million"] > 0]
    fig = go.Figure(go.Bar(x=a["usd_million"], y=a["block"], orientation="h", marker_color=INK))
    return _layout(fig, 320, title="Cost blocks by area (USD million)")
