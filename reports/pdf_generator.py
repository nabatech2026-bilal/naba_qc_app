"""
reports/pdf_generator.py
-------------------------
Generates a PDF that mirrors the layout of the client's manual paper
registers (header block, data table, defect-code key box, sign-off line),
so a printed digital report is a "ditto" match to what QC staff already
know. The NABA Tech credit line is always burned into the footer and
cannot be removed by a factory admin (mandatory, non-white-labelable).
"""

import io
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

CREDIT_LINE = "Powered by NABA Tech By Kaleem Ullah Sharif"

DEPARTMENT_TITLES = {
    "cutting": "Daily Cutting Inspection Report",
    "stitching": "Daily Inline Stitching Inspection Report",
    "checking": "Daily Checking Inspection Report",
    "packing": "Daily Packing (Pre Final) Inspection Report",
}


def build_report_pdf(report, defect_entries, factory_name: str, logo_path: str | None = None) -> bytes:
    """
    report: an InspectionReport row (or a plain object/dict with the same
            attribute names) already loaded from the DB.
    defect_entries: list of (code, label, quantity, severity) tuples.
    Returns raw PDF bytes ready to hand to st.download_button.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=10 * mm, bottomMargin=12 * mm, leftMargin=10 * mm, rightMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading2"], alignment=1, spaceAfter=2)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8)
    footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, alignment=1, textColor=colors.grey)

    elements = []

    # ---- Header block (factory name / logo left, doc meta right) ----
    header_cells = [[
        RLImage(logo_path, width=28 * mm, height=28 * mm) if logo_path else Paragraph(factory_name, styles["Heading3"]),
        Paragraph(
            f"<b>{factory_name}</b><br/>Dept.: Quality Control<br/>"
            f"Title: {DEPARTMENT_TITLES.get(report.department, 'Inspection Report')}",
            small,
        ),
        Paragraph(
            f"Report No.: {report.id}<br/>Date: {report.report_date}<br/>Hall: {report.hall.name if report.hall else ''}",
            small,
        ),
    ]]
    header_table = Table(header_cells, colWidths=[35 * mm, 150 * mm, 90 * mm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4 * mm))

    # ---- Main data row (mirrors register columns) ----
    main_headers = ["Brand", "Week", "Customer", "PO / MB", "Item", "Article Number", "Color", "Size",
                     "Total Bundle Pcs", "Sample Size", "Total Defects", "Defective %", "Status"]
    main_row = [
        getattr(report, "brand", "") or "", getattr(report, "week", "") or "",
        report.customer or "", report.po_number or "", report.design or "",
        report.article or "", report.color or "", report.size or "",
        report.total_inspected, report.sample_size, report.total_defects,
        f"{report.defective_percentage:.2f}%", report.status.value.upper() if hasattr(report.status, "value") else report.status,
    ]
    main_table = Table([main_headers, main_row], colWidths=[24 * mm] * 13)
    main_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 4 * mm))

    # ---- Defect breakdown table ----
    defect_headers = ["Code", "Defect", "Qty", "Severity"]
    defect_rows = [defect_headers] + [[c, l, str(q), s] for c, l, q, s in defect_entries]
    defect_table = Table(defect_rows, colWidths=[20 * mm, 90 * mm, 20 * mm, 30 * mm])
    defect_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(defect_table)
    elements.append(Spacer(1, 6 * mm))

    # ---- Remarks ----
    elements.append(Paragraph(f"Remarks: {report.remarks or ''}", small))
    elements.append(Spacer(1, 10 * mm))

    # ---- Sign-off row ----
    signoff = Table(
        [[f"Prepared By: {report.prepared_by or '________________'}",
          f"Checked By: {report.checked_by or '________________'}",
          f"Reviewed By: {report.reviewed_by or '________________'}"]],
        colWidths=[90 * mm, 90 * mm, 90 * mm],
    )
    signoff.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9)]))
    elements.append(signoff)
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph("Minimum Retention Time = Three Months", small))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(CREDIT_LINE, footer_style))

    doc.build(elements)
    return buf.getvalue()
