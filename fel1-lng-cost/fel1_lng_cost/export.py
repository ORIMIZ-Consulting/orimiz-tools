"""Write an estimate to an Excel workbook you can hand to a client."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .analogues import FACILITY_TYPES, SCOPES
from .estimate import EstimateResult

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)

ANALOGUE_COLUMNS = [
    ("project", "Project"),
    ("country", "Country"),
    ("site_type", "Site"),
    ("scope", "Scope"),
    ("capacity_mtpa", "Capacity (mtpa)"),
    ("cost_year", "Cost year"),
    ("cost_usd_million", "Cost (USD m, as reported)"),
    ("escalation_factor", "Escalation factor"),
    ("location_adjustment", "Location adjustment"),
    ("size_factor", "Size factor"),
    ("estimate_usd_million", "Estimate for target (USD m)"),
    ("weight_share", "Weight"),
    ("notes", "Notes"),
    ("source_url", "Source"),
]

DISCLAIMER = (
    "Concept-stage (FEL1 / AACE Class 5) screening estimate built from public "
    "analogue projects. Analogue scopes, dates and reporting bases differ. "
    "Not suitable for budget authorisation or investment decisions."
)


def _header(ws, row: int, labels: list[str]) -> None:
    for col, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=col, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def build_workbook(result: EstimateResult) -> Workbook:
    b = result.basis
    wb = Workbook()

    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "FEL1 LNG capital cost estimate"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = DISCLAIMER
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A2:D2")
    ws.row_dimensions[2].height = 45

    rows = [
        ("Inputs", None),
        ("Facility type", FACILITY_TYPES.get(b.facility_type, b.facility_type)),
        ("Capacity (mtpa)", b.capacity_mtpa),
        ("Money of year", b.estimate_year),
        ("Target location", b.target_region),
        ("Target location factor", b.target_location_factor),
        ("Escalation", "Cost index supplied" if b.cost_index else f"{b.escalation_rate:.1%} per year"),
        ("Scale exponent", b.exponent()),
        ("Scopes included", ", ".join(SCOPES.get(s, s) for s in b.scopes)),
        ("Class range", f"{b.class_low:+.0%} / {b.class_high:+.0%}"),
        (None, None),
        ("Results (USD million)", None),
        ("P10", round(result.p10_usd_million)),
        ("P50", round(result.p50_usd_million)),
        ("P90", round(result.p90_usd_million)),
        ("P50 unit cost (USD per tonne per year)", round(result.p50_unit_cost_usd_per_tpa)),
        ("Analogues used", len(result.analogues)),
    ]
    r = 4
    for label, value in rows:
        if label is not None:
            ws.cell(row=r, column=1, value=label)
            if value is None:
                ws.cell(row=r, column=1).font = BOLD
            else:
                ws.cell(row=r, column=2, value=value)
        r += 1
    if result.warnings:
        r += 1
        ws.cell(row=r, column=1, value="Notes").font = BOLD
        for w in result.warnings:
            r += 1
            ws.cell(row=r, column=1, value=w)
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 45

    wa = wb.create_sheet("Analogues")
    _header(wa, 1, [label for _, label in ANALOGUE_COLUMNS])
    for i, (_, row) in enumerate(result.analogues.iterrows(), start=2):
        for j, (key, _) in enumerate(ANALOGUE_COLUMNS, start=1):
            value = row.get(key)
            if key in ("cost_usd_million", "estimate_usd_million"):
                value = round(float(value))
            elif key in ("escalation_factor", "location_adjustment", "size_factor"):
                value = round(float(value), 3)
            elif key == "weight_share":
                value = f"{float(value):.0%}"
            elif key == "scope":
                value = SCOPES.get(value, value)
            elif value is not None and not isinstance(value, str):
                value = value.item() if hasattr(value, "item") else value
            wa.cell(row=i, column=j, value=value)
    widths = [34, 14, 12, 30, 10, 9, 14, 11, 11, 10, 16, 8, 60, 50]
    for j, width in enumerate(widths, start=1):
        wa.column_dimensions[get_column_letter(j)].width = width
    wa.freeze_panes = "B2"
    return wb


def to_excel_bytes(result: EstimateResult) -> bytes:
    buffer = BytesIO()
    build_workbook(result).save(buffer)
    return buffer.getvalue()


def to_excel_file(result: EstimateResult, path: str | Path) -> Path:
    path = Path(path)
    build_workbook(result).save(path)
    return path
