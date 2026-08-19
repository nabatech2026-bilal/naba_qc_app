"""
screens/data_entry.py
----------------------
The floor-level form. Covers all 4 departments (Cutting / Stitching /
Checking / Packing) in one screen via a department selector, since they
share the same core columns. Department-specific fields are collected
into `extra` (JSON) so nothing needs a schema change later.

Smart Auto-Fill: Article Number lives OUTSIDE the st.form (forms only
submit/rerun on their own button, so a field inside one can't reactively
trigger a lookup as you type). Typing an Article Number and pressing
Enter/Tab reruns the script; we look it up in ArticleMaster and, if found,
use its saved Item/Color/Size/Lot No/GSM as the *default* values for the
matching fields inside the form below. Lot No and GSM stay fully editable
— the auto-fill only pre-populates, it never locks the field. On submit,
whatever was actually entered gets saved back into ArticleMaster, so the
next entry for that Article Number is even more up to date.

Offline behavior: Streamlit itself needs connectivity to run, but the
"queue" concept from the spec (save to phone memory, Sync Now button) is
implemented here as a local pending-queue in st.session_state — if the DB
write fails (e.g. transient network blip to the Postgres host), the entry
is kept in the queue and a "🔄 Sync Now" button retries all queued items.
"""

import datetime as dt
import io
from PIL import Image
import streamlit as st

from auth import require_access, log_audit
from database import (
    get_session, InspectionReport, InspectionDefectEntry, DefectCode, Hall,
    LotStatus, ArticleMaster, BrandMaster,
)
from utils.aql import evaluate_lot, defective_percentage

DEPARTMENTS = {
    "cutting": "Cutting / کٹنگ",
    "stitching": "Inline Stitching / سلائی",
    "checking": "Checking / چیکنگ",
    "packing": "Packing / پیکنگ",
}

BRANDS = ["Vervial", "Brandrom", "Token fly"]
ADD_NEW_BRAND_OPTION = "➕ Other / Add New Brand..."


def _get_brand_options(factory_id: int) -> list:
    """Built-in brands + any custom brands this factory has typed before."""
    with get_session() as db:
        custom = db.query(BrandMaster).filter(BrandMaster.factory_id == factory_id).order_by(BrandMaster.name).all()
        custom_names = [c.name for c in custom]
    all_brands = BRANDS + [b for b in custom_names if b not in BRANDS]
    return all_brands


def _save_custom_brand(factory_id: int, name: str):
    """Remembers a newly typed custom brand so it appears in the dropdown next time."""
    name = (name or "").strip()
    if not name or name in BRANDS:
        return
    with get_session() as db:
        exists = db.query(BrandMaster).filter(
            BrandMaster.factory_id == factory_id, BrandMaster.name == name
        ).first()
        if not exists:
            db.add(BrandMaster(factory_id=factory_id, name=name))
            db.commit()


def _compress_image(uploaded_file, max_size=(1000, 1000), quality=60) -> bytes:
    img = Image.open(uploaded_file)
    img = img.convert("RGB")
    img.thumbnail(max_size)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def _queue_pending(payload: dict):
    st.session_state.setdefault("pending_sync_queue", [])
    st.session_state["pending_sync_queue"].append(payload)


def _sync_pending():
    queue = st.session_state.get("pending_sync_queue", [])
    if not queue:
        st.info("Nothing to sync. / سنک کرنے کے لیے کچھ نہیں۔")
        return
    remaining = []
    synced = 0
    for payload in queue:
        try:
            _save_report(payload, mark_synced=True)
            synced += 1
        except Exception:
            remaining.append(payload)
    st.session_state["pending_sync_queue"] = remaining
    st.success(f"Synced {synced} record(s). {len(remaining)} still pending.")


def _lookup_article(factory_id: int, article_number: str):
    """Returns a dict of saved specs for this Article Number, or None."""
    if not article_number:
        return None
    with get_session() as db:
        rec = db.query(ArticleMaster).filter(
            ArticleMaster.factory_id == factory_id,
            ArticleMaster.article_number == article_number.strip(),
        ).first()
        if not rec:
            return None
        return {
            "item": rec.item or "", "color": rec.color or "", "size": rec.size or "",
            "lot_no": rec.lot_no or "", "gsm": rec.gsm or "",
        }


def _upsert_article(factory_id: int, article_number: str, item, color, size, lot_no, gsm):
    """Saves/updates the specs for this Article Number so next entry auto-fills."""
    if not article_number:
        return
    with get_session() as db:
        rec = db.query(ArticleMaster).filter(
            ArticleMaster.factory_id == factory_id,
            ArticleMaster.article_number == article_number.strip(),
        ).first()
        if rec:
            rec.item, rec.color, rec.size = item, color, size
            rec.lot_no, rec.gsm = lot_no, gsm
        else:
            db.add(ArticleMaster(
                factory_id=factory_id, article_number=article_number.strip(),
                item=item, color=color, size=size, lot_no=lot_no, gsm=gsm,
            ))
        db.commit()


def _save_report(payload: dict, mark_synced: bool = True):
    with get_session() as db:
        report = InspectionReport(
            factory_id=payload["factory_id"],
            hall_id=payload["hall_id"],
            department=payload["department"],
            report_date=payload["report_date"],
            customer=payload["customer"],
            po_number=payload["po_number"],
            design=payload["design"],
            article=payload["article"],
            color=payload["color"],
            size=payload["size"],
            brand=payload["brand"],
            week=payload["week"],
            total_inspected=payload["total_inspected"],
            sample_size=payload["sample_size"],
            total_defects=payload["total_defects"],
            defective_percentage=payload["defective_percentage"],
            aql_level=payload["aql_level"],
            status=payload["status"],
            extra=payload["extra"],
            remarks=payload["remarks"],
            created_by=payload["created_by"],
            prepared_by=payload["prepared_by"],
            synced=mark_synced,
        )
        db.add(report)
        db.flush()  # get report.id before commit

        for code_id, qty, severity in payload["defect_lines"]:
            if qty and qty > 0:
                db.add(InspectionDefectEntry(
                    report_id=report.id, defect_code_id=code_id,
                    quantity=qty, severity=severity,
                ))
        db.commit()
        log_audit(payload["created_by"], "create", "inspection_reports", report.id,
                   new_value={"department": payload["department"], "status": str(payload["status"])})
        return report.id


def render():
    require_access("data_entry")
    st.header("📋 QC Data Entry / QC ڈیٹا انٹری")

    factory_id = st.session_state["factory_id"]
    user_id = st.session_state["user_id"]

    col_sync, _ = st.columns([1, 4])
    with col_sync:
        pending_count = len(st.session_state.get("pending_sync_queue", []))
        if st.button(f"🔄 Sync Now ({pending_count} pending)"):
            _sync_pending()

    department = st.selectbox("Department / شعبہ", list(DEPARTMENTS.keys()),
                               format_func=lambda d: DEPARTMENTS[d])

    with get_session() as db:
        from database import Unit, Destination
        halls = (
            db.query(Hall)
            .join(Unit, Hall.unit_id == Unit.id)
            .join(Destination, Unit.destination_id == Destination.id)
            .filter(Destination.factory_id == factory_id)
            .all()
        )
        hall_options = {h.id: f"{h.unit.destination.name} / {h.unit.name} / {h.name}" for h in halls}

        defect_codes = (
            db.query(DefectCode)
            .filter(DefectCode.factory_id == factory_id, DefectCode.department == department,
                    DefectCode.is_active == True)  # noqa: E712
            .order_by(DefectCode.code)
            .all()
        )
        defect_codes_data = [(dc.id, dc.code, dc.label, dc.default_severity) for dc in defect_codes]

    if not hall_options:
        st.warning("No halls set up yet. Ask your Admin to add Destination → Unit → Hall first. / "
                    "ابھی کوئی ہال سیٹ نہیں کیا گیا، پہلے ایڈمن سے ڈسٹینیشن → یونٹ → ہال شامل کروائیں۔")
        return

    # --- Article Number lives OUTSIDE the form so we can react to it and
    # auto-fill the fields below (a widget inside st.form only "fires" on
    # the form's own submit button, so lookup has to happen before the form).
    article_number = st.text_input(
        "Article Number / آرٹیکل نمبر",
        key="de_article_number",
        help="Type the Article Number and press Enter — if it's been used before, "
             "Item/Color/Size/Lot No/GSM below will auto-fill from the last entry.",
    )
    saved_specs = _lookup_article(factory_id, article_number) or {}
    if article_number and saved_specs:
        st.caption("✅ Found saved specs for this Article Number — auto-filled below (Lot No / GSM still editable).")
    elif article_number:
        st.caption("ℹ️ New Article Number — specs will be saved after you submit, for next time.")

    # --- Brand also lives OUTSIDE the form so picking "Add New Brand"
    # immediately reveals the custom text input (a form only reruns on its
    # own submit button, so this couldn't react inside the form).
    brand_options = _get_brand_options(factory_id) + [ADD_NEW_BRAND_OPTION]
    brand_choice = st.selectbox("Brand / برانڈ", brand_options, key="de_brand_choice")
    if brand_choice == ADD_NEW_BRAND_OPTION:
        custom_brand = st.text_input("New Brand Name / نیا برانڈ نام", key="de_custom_brand")
        brand = custom_brand.strip()
    else:
        brand = brand_choice

    with st.form("qc_entry_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        hall_id = c1.selectbox("Hall / ہال", list(hall_options.keys()), format_func=lambda h: hall_options[h])
        report_date = c2.date_input("Date / تاریخ", value=dt.date.today())
        customer = c3.text_input("Customer")

        c5, c6 = st.columns(2)
        week = c5.text_input("Week / ہفتہ")
        po_number = c6.text_input("PO / MB")

        c7, c8, c9 = st.columns(3)
        item = c7.text_input("Item", value=saved_specs.get("item", ""))
        color = c8.text_input("Color", value=saved_specs.get("color", ""))
        size = c9.text_input("Size", value=saved_specs.get("size", ""))

        c10, c11 = st.columns(2)
        lot_no = c10.text_input("Lot No (auto-filled, editable)", value=saved_specs.get("lot_no", ""))
        gsm = c11.text_input("GSM (auto-filled, editable)", value=saved_specs.get("gsm", ""))

        total_inspected = st.number_input("Total Bundle Pcs", min_value=0, step=1)
        sample_size = st.number_input("Sample Size (leave 0 to auto-calc from AQL table)", min_value=0, step=1)

        st.markdown("**Department-specific fields**")
        extra = {"lot_no": lot_no, "gsm": gsm}
        if department == "cutting":
            e1, e2 = st.columns(2)
            extra["fabric_width"] = e1.text_input("Fabric Width")
            extra["ply_height"] = e2.text_input("Ply Height")
        elif department == "stitching":
            e1, e2 = st.columns(2)
            extra["machine_no"] = e1.text_input("Machine No")
            extra["operation_no"] = e2.text_input("Operation No")
        elif department == "checking":
            extra["checker_no"] = st.text_input("Checker #")
        elif department == "packing":
            extra["table_no"] = st.text_input("Table No")

        st.markdown("**Defects found (enter quantity per code)**")
        defect_qty = {}
        if defect_codes_data:
            cols = st.columns(3)
            for i, (code_id, code, label, severity) in enumerate(defect_codes_data):
                with cols[i % 3]:
                    qty = st.number_input(f"{code}. {label}", min_value=0, step=1, key=f"defect_{code_id}")
                    defect_qty[code_id] = (qty, severity)
        else:
            st.info("No defect codes set up for this department yet.")

        photo = st.file_uploader("Defective piece photo (optional) / خراب پیس کی تصویر", type=["jpg", "jpeg", "png"])
        remarks = st.text_area("Remarks / ریمارکس")
        prepared_by = st.text_input("Prepared By (Quality Controller)")

        submitted = st.form_submit_button("✅ Submit / جمع کروائیں")

    if submitted:
        if brand_choice == ADD_NEW_BRAND_OPTION and not brand:
            st.error("Please type the new brand name above before submitting. / براہ کرم نیا برانڈ نام لکھیں۔")
            st.stop()

        total_defects = sum(q for q, _ in defect_qty.values())
        eff_sample_size = sample_size if sample_size > 0 else total_inspected
        major_count = sum(q for q, sev in defect_qty.values() if sev.value == "major")
        minor_count = sum(q for q, sev in defect_qty.values() if sev.value == "minor")
        critical_count = sum(q for q, sev in defect_qty.values() if sev.value == "critical")

        aql_result = evaluate_lot(
            lot_size=max(total_inspected, 1),
            major_defects=major_count + critical_count,  # critical treated at least as strict as major
            minor_defects=minor_count,
        )
        status = LotStatus.PASS if aql_result.status == "PASS" and critical_count == 0 else LotStatus.FAIL
        pct = defective_percentage(total_inspected, total_defects)

        payload = {
            "factory_id": factory_id,
            "hall_id": hall_id,
            "department": department,
            "report_date": report_date,
            "customer": customer,
            "po_number": po_number,
            "design": item,
            "article": article_number,
            "color": color,
            "size": size,
            "brand": brand,
            "week": week,
            "total_inspected": total_inspected,
            "sample_size": eff_sample_size,
            "total_defects": total_defects,
            "defective_percentage": pct,
            "aql_level": f"MAJ {2.5}, MIN {4.0}",
            "status": status,
            "extra": extra,
            "remarks": remarks,
            "created_by": user_id,
            "prepared_by": prepared_by,
            "defect_lines": [(cid, q, sev) for cid, (q, sev) in defect_qty.items()],
        }

        if photo is not None:
            _compress_image(photo)  # compressed bytes would be uploaded to object storage in production

        try:
            report_id = _save_report(payload, mark_synced=True)
            # Remember this Article Number's specs for next time (auto-fill).
            _upsert_article(factory_id, article_number, item, color, size, lot_no, gsm)
            # Remember a newly typed custom brand so it appears in the dropdown next time.
            _save_custom_brand(factory_id, brand)
            st.success(f"Saved ✅ Report #{report_id} — Lot Status: **{status.value.upper()}** "
                       f"({aql_result.reason})")
        except Exception as e:
            _queue_pending(payload)
            st.warning(f"⚠️ Could not reach the server — saved locally and queued for sync. "
                       f"Press '🔄 Sync Now' once you're back online. ({e})")
