"""
screens/admin.py
----------------
Admin panel for managing users, locations, defect codes, PDF report options, and audit logs.
"""

from types import SimpleNamespace
import streamlit as st

from auth import require_access, log_audit
from database import (
    get_session, User, Factory, Destination, Unit, Hall,
    DefectCode, AuditLog, InspectionReport, InspectionDefectEntry
)
from utils.pdf_generator import build_report_pdf


def _user_management():
    st.subheader("👥 User Management / یوزر مینجمنٹ")
    factory_id = st.session_state["factory_id"]

    with get_session() as db:
        users = db.query(User).filter(User.factory_id == factory_id).all()
        user_list = [
            {
                "ID": u.id,
                "Username": u.username,
                "Role": u.role,
                "Active": u.is_active,
            }
            for u in users
        ]
        st.dataframe(user_list, use_container_width=True)

    with st.expander("➕ Add New User / نیا یوزر بنائیں"):
        with st.form("add_user_form"):
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["inspector", "admin", "main_admin"])
            submitted = st.form_submit_button("Create User / یوزر بنائیں")

            if submitted:
                if not new_username or not new_password:
                    st.error("Username and password are required.")
                else:
                    with get_session() as db:
                        from auth import hash_password
                        existing = db.query(User).filter(User.username == new_username).first()
                        if existing:
                            st.error("Username already exists.")
                        else:
                            u = User(
                                username=new_username,
                                password_hash=hash_password(new_password),
                                role=new_role,
                                factory_id=factory_id,
                                is_active=True,
                            )
                            db.add(u)
                            db.commit()
                            log_audit(st.session_state["user_id"], "create", "users", u.id)
                            st.success(f"User {new_username} created successfully!")
                            st.rerun()


def _location_management():
    st.subheader("🏢 Location Hierarchy / لوکیشن مینجمنٹ")
    factory_id = st.session_state["factory_id"]

    t1, t2, t3 = st.tabs(["Destinations", "Units", "Halls"])

    with t1:
        st.markdown("**Destinations**")
        with get_session() as db:
            dests = db.query(Destination).filter(Destination.factory_id == factory_id).all()
            for d in dests:
                st.write(f"• **{d.name}**")

        with st.form("add_dest_form"):
            dest_name = st.text_input("Destination Name (e.g. Export / Local)")
            if st.form_submit_button("Add Destination") and dest_name:
                with get_session() as db:
                    db.add(Destination(factory_id=factory_id, name=dest_name))
                    db.commit()
                    st.success(f"Destination '{dest_name}' added.")
                    st.rerun()

    with t2:
        st.markdown("**Units**")
        with get_session() as db:
            dests = db.query(Destination).filter(Destination.factory_id == factory_id).all()
            dest_map = {d.name: d.id for d in dests}

        if dest_map:
            sel_dest = st.selectbox("Select Destination for Unit", list(dest_map.keys()))
            with st.form("add_unit_form"):
                unit_name = st.text_input("Unit Name (e.g. Unit 1)")
                if st.form_submit_button("Add Unit") and unit_name:
                    with get_session() as db:
                        db.add(Unit(destination_id=dest_map[sel_dest], name=unit_name))
                        db.commit()
                        st.success(f"Unit '{unit_name}' added under {sel_dest}.")
                        st.rerun()
        else:
            st.info("Please create a Destination first.")

    with t3:
        st.markdown("**Halls**")
        with get_session() as db:
            units = (
                db.query(Unit)
                .join(Destination)
                .filter(Destination.factory_id == factory_id)
                .all()
            )
            unit_map = {f"{u.destination.name} -> {u.name}": u.id for u in units}

        if unit_map:
            sel_unit = st.selectbox("Select Unit for Hall", list(unit_map.keys()))
            with st.form("add_hall_form"):
                hall_name = st.text_input("Hall Name (e.g. Hall A)")
                if st.form_submit_button("Add Hall") and hall_name:
                    with get_session() as db:
                        db.add(Hall(unit_id=unit_map[sel_unit], name=hall_name))
                        db.commit()
                        st.success(f"Hall '{hall_name}' added.")
                        st.rerun()
        else:
            st.info("Please create a Unit first.")


def _defect_code_management():
    st.subheader("🏷️ Defect Code Management / ڈیفیکٹ کوڈز")
    factory_id = st.session_state["factory_id"]

    department = st.selectbox(
        "Department",
        ["cutting", "stitching", "checking", "knitting", "dyeing", "packing"],
        key="dcm_dept",
    )

    with get_session() as db:
        codes = (
            db.query(DefectCode)
            .filter(DefectCode.factory_id == factory_id, DefectCode.department == department)
            .all()
        )
        code_data = [
            {
                "ID": c.id,
                "Code": c.code,
                "Label": c.label,
                "Severity": str(c.default_severity.value if hasattr(c.default_severity, 'value') else c.default_severity),
                "Active": c.is_active,
            }
            for c in codes
        ]
        st.dataframe(code_data, use_container_width=True)

    with st.expander("➕ Add New Defect Code"):
        with st.form("add_defect_code_form"):
            code = st.text_input("Defect Code (e.g. A, B, C)")
            label = st.text_input("Defect Description / لسٹ کا نام")
            severity = st.selectbox("Severity", ["minor", "major", "critical"])
            submitted = st.form_submit_button("Save Defect Code")

            if submitted and code and label:
                from database import SeverityLevel
                with get_session() as db:
                    dc = DefectCode(
                        factory_id=factory_id,
                        department=department,
                        code=code.upper(),
                        label=label,
                        default_severity=SeverityLevel(severity) if hasattr(SeverityLevel, 'minor') else severity,
                        is_active=True,
                    )
                    db.add(dc)
                    db.commit()
                    st.success(f"Defect code {code} added for {department}!")
                    st.rerun()


def _reports_export():
    st.subheader("📄 PDF Reports & Export / پی ڈی ایف رپورٹ")
    factory_id = st.session_state["factory_id"]

    with get_session() as db:
        reports = (
            db.query(InspectionReport)
            .filter(InspectionReport.factory_id == factory_id)
            .order_by(InspectionReport.id.desc())
            .limit(50)
            .all()
        )
        if not reports:
            st.info("No inspection reports found.")
            return

        report_map = {
            f"Report #{r.id} | {r.report_date} | {r.department} | {r.article}": r.id
            for r in reports
        }
        chosen_key = st.selectbox("Select Report to Export PDF", list(report_map.keys()))
        chosen_id = report_map[chosen_key]

        chosen = db.query(InspectionReport).filter(InspectionReport.id == chosen_id).first()
        entries = (
            db.query(InspectionDefectEntry)
            .filter(InspectionDefectEntry.report_id == chosen_id)
            .all()
        )
        factory = db.query(Factory).filter(Factory.id == factory_id).first()

        report_snapshot = SimpleNamespace(
            id=chosen.id,
            department=chosen.department,
            report_date=chosen.report_date,
            customer=chosen.customer,
            po_number=chosen.po_number,
            design=chosen.design,
            article=chosen.article,
            color=chosen.color,
            size=chosen.size,
            brand=chosen.brand,
            week=chosen.week,
            total_inspected=chosen.total_inspected,
            sample_size=chosen.sample_size,
            total_defects=chosen.total_defects,
            defective_percentage=chosen.defective_percentage,
            status=chosen.status,
            remarks=chosen.remarks,
            prepared_by=chosen.prepared_by,
            checked_by=chosen.checked_by,
            reviewed_by=chosen.reviewed_by,
            hall=SimpleNamespace(name=chosen.hall.name if chosen.hall else ""),
        )

        factory_name = factory.name if factory else ""
        logo_path = factory.logo_path if factory else None

    pdf_bytes = build_report_pdf(report_snapshot, entries, factory_name, logo_path)
    st.download_button(
        "📥 Download PDF",
        data=pdf_bytes,
        file_name=f"report_{chosen_id}_{report_snapshot.department}.pdf",
        mime="application/pdf",
    )


def _audit_log():
    st.subheader("📜 System Audit Log / سسٹم آڈٹ لاگ")
    factory_id = st.session_state["factory_id"]

    with get_session() as db:
        logs = (
            db.query(AuditLog)
            .join(User)
            .filter(User.factory_id == factory_id)
            .order_by(AuditLog.id.desc())
            .limit(100)
            .all()
        )
        log_data = [
            {
                "Time": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "",
                "User": l.user.username if l.user else "",
                "Action": l.action,
                "Table": l.target_table,
                "Record ID": l.target_id,
            }
            for l in logs
        ]
        st.dataframe(log_data, use_container_width=True)


def render():
    require_access("admin")
    st.title("⚙️ Admin Panel / ایڈمن پینل")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Users", "Locations", "Defect Codes", "Reports / PDF", "Audit Log"
    ])

    with tab1:
        _user_management()
    with tab2:
        _location_management()
    with tab3:
        _defect_code_management()
    with tab4:
        _reports_export()
    with tab5:
        _audit_log()