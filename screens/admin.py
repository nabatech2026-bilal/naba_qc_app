"""
screens/admin.py
------------------
Covers everything a Main Admin / Assistant Admin (and, scoped down, a Hall
Manager) needs day-to-day:
  - Create/deactivate sub-users, reset their passwords (never reveals the
    admin's own password to anyone — delegated admins get their OWN login).
  - Manage Destination -> Unit -> Hall location tree.
  - Edit the per-department defect-code library (Dynamic Defects).
  - White-label settings (factory name, logo, senior officer names).
  - Download a register-matching PDF for any saved report.
  - View the audit log (who changed/deleted what).
"""

import streamlit as st
from types import SimpleNamespace
from sqlalchemy.orm import joinedload

from auth import require_access, can_manage_user, hash_password, log_audit, current_role
from database import (
    get_session, User, UserRole, Destination, Unit, Hall, Factory,
    DefectCode, Severity, InspectionReport, AuditLog
)
from reports.pdf_generator import build_report_pdf


def _user_management():
    st.subheader("👤 User Management / یوزر مینجمنٹ")
    factory_id = st.session_state["factory_id"]
    actor_role = current_role()

    with get_session() as db:
        users = db.query(User).filter(User.factory_id == factory_id).all()
        halls = (
            db.query(Hall).join(Unit, Hall.unit_id == Unit.id)
            .join(Destination, Unit.destination_id == Destination.id)
            .filter(Destination.factory_id == factory_id).all()
        )
        hall_options = {h.id: f"{h.unit.destination.name}/{h.unit.name}/{h.name}" for h in halls}

        st.dataframe(
            [{"Username": u.username, "Name": u.full_name, "Role": u.role.value,
              "Hall": hall_options.get(u.hall_id, "-"), "Active": u.is_active} for u in users],
            use_container_width=True,
        )

    st.markdown("**Create new user**")
    assignable_roles = [r for r in UserRole if r != UserRole.SUPER_MASTER_ADMIN and can_manage_user(r.value)]
    if not assignable_roles:
        st.info("You don't have permission to create new users.")
        return

    with st.form("create_user_form"):
        c1, c2 = st.columns(2)
        full_name = c1.text_input("Full Name")
        username = c2.text_input("Username")
        c3, c4 = st.columns(2)
        role = c3.selectbox("Role", assignable_roles, format_func=lambda r: r.value)
        hall_id = c4.selectbox(
            "Hall (for Hall Manager / Floor Inspector)",
            [None] + list(hall_options.keys()),
            format_func=lambda h: "—" if h is None else hall_options[h],
        )
        temp_password = st.text_input("Temporary Password", type="password")
        submitted = st.form_submit_button("Create User")

    if submitted:
        if not (full_name and username and temp_password):
            st.error("Please fill all fields.")
        else:
            with get_session() as db:
                exists = db.query(User).filter(User.factory_id == factory_id, User.username == username).first()
                if exists:
                    st.error("Username already exists in this factory.")
                else:
                    new_user = User(
                        factory_id=factory_id, username=username, full_name=full_name,
                        role=role, hall_id=hall_id, password_hash=hash_password(temp_password),
                        created_by=st.session_state["user_id"], must_reset_password=True,
                    )
                    db.add(new_user)
                    db.flush()
                    log_audit(st.session_state["user_id"], "create", "users", new_user.id,
                               new_value={"username": username, "role": role.value})
                    st.success(f"User '{username}' created. They must reset their password on first login.")

    st.markdown("**Reset a user's password**")
    with get_session() as db:
        users = db.query(User).filter(User.factory_id == factory_id).all()
        resettable = [{"id": u.id, "username": u.username, "role": u.role.value}
                      for u in users if can_manage_user(u.role.value)]
    if resettable:
        id_to_label = {u["id"]: f"{u['username']} ({u['role']})" for u in resettable}
        target_id = st.selectbox("User", list(id_to_label.keys()), format_func=lambda i: id_to_label[i])
        new_pw = st.text_input("New temporary password", type="password", key="reset_pw")
        if st.button("Reset Password"):
            with get_session() as db:
                u = db.query(User).get(target_id)
                u.password_hash = hash_password(new_pw)
                u.must_reset_password = True
                db.commit()
                log_audit(st.session_state["user_id"], "update", "users", u.id,
                           old_value={"password_hash": "***"}, new_value={"password_hash": "***"})
            st.success("Password reset. Share it with the user securely.")
    else:
        st.caption("No users you're permitted to manage yet.")

    st.markdown("---")
    st.markdown("**🗑️ Delete a user**")
    with get_session() as db:
        users = db.query(User).filter(User.factory_id == factory_id).all()
        deletable = [{"id": u.id, "username": u.username, "role": u.role.value}
                     for u in users if can_manage_user(u.role.value)]
    if deletable:
        id_to_label_del = {u["id"]: f"{u['username']} ({u['role']})" for u in deletable}
        target_del_id = st.selectbox("User to delete", list(id_to_label_del.keys()),
                                      format_func=lambda i: id_to_label_del[i], key="del_user_select")
        target_del_username = next(u["username"] for u in deletable if u["id"] == target_del_id)
        confirm = st.checkbox(f"I confirm I want to permanently delete '{target_del_username}'", key="del_user_confirm")
        if st.button("🗑️ Delete User", type="primary", disabled=not confirm):
            with get_session() as db:
                u = db.query(User).get(target_del_id)
                deleted_username = u.username
                deleted_role = u.role.value
                db.delete(u)
                db.commit()
            log_audit(st.session_state["user_id"], "delete", "users", target_del_id,
                       old_value={"username": deleted_username, "role": deleted_role})
            st.success(f"User '{deleted_username}' deleted.")
            st.rerun()
    else:
        st.caption("No users you're permitted to delete.")


def _location_management():
    st.subheader("📍 Locations (Destination → Unit → Hall)")
    factory_id = st.session_state["factory_id"]

    with get_session() as db:
        destinations = db.query(Destination).filter(Destination.factory_id == factory_id).all()
        dest_snapshots = [{"id": d.id, "name": d.name} for d in destinations]

    with st.expander("➕ Add Destination"):
        name = st.text_input("Destination name (e.g. Sohrab Goth)", key="dest_name")
        if st.button("Add Destination"):
            with get_session() as db:
                db.add(Destination(factory_id=factory_id, name=name))
            st.success("Added.")
            st.rerun()

    for dest in dest_snapshots:
        with st.expander(f"🏭 {dest['name']}"):
            with get_session() as db:
                units = db.query(Unit).filter(Unit.destination_id == dest["id"]).all()
                unit_snapshots = [{"id": u.id, "name": u.name} for u in units]
            unit_name = st.text_input(f"New unit under {dest['name']}", key=f"unit_{dest['id']}")
            if st.button(f"Add Unit to {dest['name']}", key=f"add_unit_{dest['id']}"):
                with get_session() as db:
                    db.add(Unit(destination_id=dest["id"], name=unit_name))
                st.rerun()

            for unit in unit_snapshots:
                st.markdown(f"**Unit: {unit['name']}**")
                with get_session() as db:
                    halls = db.query(Hall).filter(Hall.unit_id == unit["id"]).all()
                    hall_names = [h.name for h in halls]
                st.write(", ".join(hall_names) or "No halls yet")
                hall_name = st.text_input(f"New hall under {unit['name']}", key=f"hall_{unit['id']}")
                if st.button(f"Add Hall to {unit['name']}", key=f"add_hall_{unit['id']}"):
                    with get_session() as db:
                        db.add(Hall(unit_id=unit["id"], name=hall_name))
                    st.rerun()


def _defect_code_management():
    st.subheader("🏷️ Defect Code Management / ڈیفیکٹ کوڈز")
    factory_id = st.session_state["factory_id"]
    department = st.selectbox("Department", ["cutting", "stitching", "checking", "packing"], key="dcm_dept")

    with get_session() as db:
        codes = (
            db.query(DefectCode)
            .filter(DefectCode.factory_id == factory_id, DefectCode.department == department)
            .order_by(DefectCode.code).all()
        )
        st.dataframe(
            [{"Code": c.code, "Label": c.label, "Severity": c.default_severity.value, "Active": c.is_active} for c in codes],
            use_container_width=True,
        )

    with st.form("add_defect_code"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("Code (e.g. AJ)")
        label = c2.text_input("Label")
        severity = c3.selectbox("Default Severity", list(Severity), format_func=lambda s: s.value)
        if st.form_submit_button("Add Defect Code"):
            with get_session() as db:
                db.add(DefectCode(factory_id=factory_id, department=department, code=code,
                                   label=label, default_severity=severity))
            st.success("Added.")
            st.rerun()


def _white_label_settings():
    st.subheader("🎨 White-Label Settings / برانڈنگ سیٹنگز")
    factory_id = st.session_state["factory_id"]
    with get_session() as db:
        factory = db.query(Factory).get(factory_id)
        with st.form("white_label_form"):
            name = st.text_input("Factory Name", value=factory.name)
            gm = st.text_input("GM Quality", value=factory.gm_quality_name or "")
            qc_mgr = st.text_input("QC Manager / DM", value=factory.qc_manager_name or "")
            admin_name = st.text_input("Admin Name", value=factory.admin_name or "")
            logo = st.file_uploader("Upload new logo", type=["png", "jpg", "jpeg"])
            if st.form_submit_button("Save"):
                factory.name = name
                factory.gm_quality_name = gm
                factory.qc_manager_name = qc_mgr
                factory.admin_name = admin_name
                if logo is not None:
                    path = f"assets/logo_factory_{factory_id}.png"
                    with open(path, "wb") as f:
                        f.write(logo.read())
                    factory.logo_path = path
                db.commit()
                st.success("Saved.")
    st.caption("Note: the 'Powered by NABA Tech By Kaleem Ullah Sharif' credit on the footer and every "
               "PDF report is fixed and cannot be changed here.")


def _reports_export():
    st.subheader("🖨️ Reports / PDF Export")
    factory_id = st.session_state["factory_id"]
    with get_session() as db:
        reports = (
            db.query(InspectionReport)
            .options(joinedload(InspectionReport.hall), joinedload(InspectionReport.defect_entries))
            .filter(InspectionReport.factory_id == factory_id)
            .order_by(InspectionReport.report_date.desc())
            .limit(200).all()
        )
        factory = db.query(Factory).get(factory_id)
        if not reports:
            st.info("No reports yet.")
            return

        # Pick by ID (not by passing live ORM objects to the widget) so the
        # selection survives Streamlit reruns without touching a closed session.
        id_to_label = {
            r.id: f"#{r.id} — {r.department} — {r.report_date} — {r.customer or ''}" for r in reports
        }
        chosen_id = st.selectbox("Select a report", list(id_to_label.keys()),
                                  format_func=lambda i: id_to_label[i])
        chosen = next(r for r in reports if r.id == chosen_id)

        # Snapshot everything we need into plain objects WHILE the session is
        # still open, so build_report_pdf never touches a lazy attribute
        # after this "with" block ends (that was the DetachedInstanceError).
        entries = [
            (e.defect_code.code, e.defect_code.label, e.quantity, e.severity.value)
            for e in chosen.defect_entries
        ]
        report_snapshot = SimpleNamespace(
            id=chosen.id, department=chosen.department, report_date=chosen.report_date,
            customer=chosen.customer, po_number=chosen.po_number, design=chosen.design,
            article=chosen.article, color=chosen.color, size=chosen.size,
            brand=chosen.brand, week=chosen.week,
            total_inspected=chosen.total_inspected, sample_size=chosen.sample_size,
            total_defects=chosen.total_defects, defective_percentage=chosen.defective_percentage,
            status=chosen.status, remarks=chosen.remarks, prepared_by=chosen.prepared_by,
            checked_by=chosen.checked_by, reviewed_by=chosen.reviewed_by,
            hall=SimpleNamespace(name=chosen.hall.name if chosen.hall else ""),
        )
        factory_name = factory.name
        logo_path = factory.logo_path

    # Outside the session now — everything used below is a plain snapshot.
    pdf_bytes = build_report_pdf(report_snapshot, entries, factory_name, logo_path)
    st.download_button("⬇️ Download PDF", data=pdf_bytes,
                        file_name=f"report_{chosen_id}_{report_snapshot.department}.pdf", mime="application/pdf")


def _audit_log():
    st.subheader("🔒 Audit Log")
    with get_session() as db:
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(300).all()
        st.dataframe(
            [{"Time": l.timestamp, "User ID": l.user_id, "Action": l.action,
              "Table": l.table_name, "Record ID": l.record_id} for l in logs],
            use_container_width=True,
        )


def render():
    require_access("user_management") if current_role() != "hall_manager" else require_access("hall_user_management")
    st.header("⚙️ Admin Panel / ایڈمن پینل")

    role = current_role()
    tabs_map = [("Users", _user_management), ("Locations", _location_management),
                ("Defect Codes", _defect_code_management), ("Reports / PDF", _reports_export)]
    if role in ("main_admin", "assistant_admin"):
        tabs_map.insert(3, ("White-Label", _white_label_settings))
        tabs_map.append(("Audit Log", _audit_log))

    tabs = st.tabs([t[0] for t in tabs_map])
    for tab, (_, func) in zip(tabs, tabs_map):
        with tab:
            func()
