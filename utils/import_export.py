"""
utils/import_export.py
------------------------
Bulk Import / Export for InspectionReport data (mandatory per spec).

Export: pulls all reports (with defect line items flattened) for a
factory/date range into an Excel workbook whose columns mirror the manual
register fields, so factory staff can open it directly in Excel/Google
Sheets.

Import: accepts an Excel/CSV file built from the same template
(download the template first via `build_import_template`) and bulk-creates
InspectionReport + InspectionDefectEntry rows. Rows that fail validation
are skipped and reported back to the user instead of aborting the whole
batch.
"""

import io
import datetime as dt
import pandas as pd

from database import get_session, InspectionReport, InspectionDefectEntry, DefectCode, Hall, LotStatus
from utils.aql import evaluate_lot, defective_percentage

EXPORT_COLUMNS = [
    "report_id", "department", "date", "hall", "customer", "po_number",
    "design", "article", "color", "size", "total_inspected", "sample_size",
    "total_defects", "defective_percentage", "aql_level", "status",
    "prepared_by", "checked_by", "reviewed_by", "remarks",
]

IMPORT_TEMPLATE_COLUMNS = [
    "department", "date", "hall_name", "customer", "po_number", "design",
    "article", "color", "size", "total_inspected", "sample_size",
    "prepared_by", "remarks",
    # defect columns are appended dynamically per department when the
    # template is generated for a specific factory (one column per defect code)
]


def export_reports_to_excel(factory_id: int, date_from: dt.date, date_to: dt.date,
                             department: str | None = None) -> bytes:
    """Returns an .xlsx file (bytes) with one row per report and defect quantities as extra columns."""
    with get_session() as db:
        q = (
            db.query(InspectionReport)
            .filter(InspectionReport.factory_id == factory_id,
                    InspectionReport.report_date >= date_from,
                    InspectionReport.report_date <= date_to)
        )
        if department and department != "All":
            q = q.filter(InspectionReport.department == department)
        reports = q.order_by(InspectionReport.report_date).all()

        rows = []
        for r in reports:
            row = {
                "report_id": r.id, "department": r.department, "date": r.report_date,
                "hall": r.hall.name if r.hall else "", "customer": r.customer,
                "brand": r.brand, "week": r.week,
                "po_number": r.po_number, "design": r.design, "article": r.article,
                "color": r.color, "size": r.size, "total_inspected": r.total_inspected,
                "sample_size": r.sample_size, "total_defects": r.total_defects,
                "defective_percentage": r.defective_percentage, "aql_level": r.aql_level,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "prepared_by": r.prepared_by, "checked_by": r.checked_by,
                "reviewed_by": r.reviewed_by, "remarks": r.remarks,
            }
            # one column per defect code with the quantity found on this report
            for entry in r.defect_entries:
                row[f"defect_{entry.defect_code.code}_{entry.defect_code.label}"] = entry.quantity
            rows.append(row)

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Inspection Reports")
    return buf.getvalue()


def build_import_template(factory_id: int, department: str) -> bytes:
    """
    Generates a blank Excel template with the base columns PLUS one column
    per active defect code for the chosen department, so the person filling
    it in just types quantities under each defect heading — same mental
    model as the paper register.
    """
    with get_session() as db:
        codes = (
            db.query(DefectCode)
            .filter(DefectCode.factory_id == factory_id, DefectCode.department == department,
                    DefectCode.is_active == True)  # noqa: E712
            .order_by(DefectCode.code).all()
        )
        columns = IMPORT_TEMPLATE_COLUMNS + [f"defect_{c.code}_{c.label}" for c in codes]

    df = pd.DataFrame(columns=columns)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Import Template")
    return buf.getvalue()


def import_reports_from_file(factory_id: int, department: str, uploaded_file,
                              created_by: int) -> tuple[int, list[str]]:
    """
    Reads an Excel/CSV file built from build_import_template() and bulk
    inserts reports. Returns (success_count, list_of_error_messages).
    """
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    errors = []
    success_count = 0

    with get_session() as db:
        halls = {
            h.name: h.id
            for h in db.query(Hall).join(Hall.unit).join(Hall.unit.property.mapper.class_.destination)
        } if False else {}
        # simpler explicit join to avoid relationship-path ambiguity
        from database import Unit, Destination
        halls = {
            h.name: h.id
            for h in (
                db.query(Hall)
                .join(Unit, Hall.unit_id == Unit.id)
                .join(Destination, Unit.destination_id == Destination.id)
                .filter(Destination.factory_id == factory_id)
                .all()
            )
        }
        defect_codes = {
            f"defect_{c.code}_{c.label}": (c.id, c.default_severity)
            for c in db.query(DefectCode).filter(
                DefectCode.factory_id == factory_id, DefectCode.department == department
            ).all()
        }
        defect_columns = [col for col in df.columns if col.startswith("defect_")]

        for idx, row in df.iterrows():
            try:
                hall_name = str(row.get("hall_name", "")).strip()
                if hall_name not in halls:
                    errors.append(f"Row {idx + 2}: hall '{hall_name}' not found — skipped.")
                    continue

                total_inspected = int(row.get("total_inspected", 0) or 0)
                sample_size = int(row.get("sample_size", 0) or total_inspected)

                defect_lines = []
                major_count = minor_count = critical_count = 0
                for col in defect_columns:
                    qty = row.get(col)
                    if pd.isna(qty) or int(qty) <= 0:
                        continue
                    qty = int(qty)
                    if col not in defect_codes:
                        errors.append(f"Row {idx + 2}: unknown defect column '{col}' — skipped column.")
                        continue
                    code_id, severity = defect_codes[col]
                    defect_lines.append((code_id, qty, severity))
                    if severity.value == "major":
                        major_count += qty
                    elif severity.value == "minor":
                        minor_count += qty
                    elif severity.value == "critical":
                        critical_count += qty

                total_defects = sum(q for _, q, _ in defect_lines)
                aql_result = evaluate_lot(max(total_inspected, 1), major_count + critical_count, minor_count)
                status = LotStatus.PASS if aql_result.status == "PASS" and critical_count == 0 else LotStatus.FAIL

                report_date = pd.to_datetime(row.get("date")).date() if not pd.isna(row.get("date")) else dt.date.today()

                report = InspectionReport(
                    factory_id=factory_id, hall_id=halls[hall_name], department=department,
                    report_date=report_date, customer=row.get("customer"), po_number=row.get("po_number"),
                    design=row.get("design"), article=row.get("article"), color=row.get("color"),
                    size=row.get("size"), total_inspected=total_inspected, sample_size=sample_size,
                    total_defects=total_defects,
                    defective_percentage=defective_percentage(total_inspected, total_defects),
                    aql_level="MAJ 2.5, MIN 4.0", status=status, remarks=row.get("remarks"),
                    prepared_by=row.get("prepared_by"), created_by=created_by, synced=True,
                )
                db.add(report)
                db.flush()
                for code_id, qty, severity in defect_lines:
                    db.add(InspectionDefectEntry(report_id=report.id, defect_code_id=code_id,
                                                  quantity=qty, severity=severity))
                success_count += 1
            except Exception as e:
                errors.append(f"Row {idx + 2}: {e}")

        db.commit()

    return success_count, errors
