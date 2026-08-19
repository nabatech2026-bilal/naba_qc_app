"""
screens/super_admin.py
------------------------
The hidden, cross-factory control panel. This screen is never linked from
any factory's normal navigation — it only renders for a logged-in
SUPER_MASTER_ADMIN user (see auth.ROLE_PERMISSIONS), whose account has no
factory_id at all and is created once via the seed script (see seed.py),
not through the normal sign-up flow.
"""

import datetime as dt
import streamlit as st

from auth import require_access, hash_password, log_audit
from database import get_session, Factory, User, UserRole
from utils.defect_codes import seed_defect_codes_for_factory


def render():
    require_access("super_panel")
    st.header("🛡️ Super Master Admin / سپر ماسٹر ایڈمن")
    st.caption("Hidden control panel — not visible to any factory client.")

    tab1, tab2, tab3 = st.tabs(["Factories", "Create Factory", "License Control"])

    with tab1:
        with get_session() as db:
            factories = db.query(Factory).all()
            st.dataframe(
                [{"ID": f.id, "Name": f.name, "License Expiry": f.license_expiry,
                  "Active": f.is_active} for f in factories],
                use_container_width=True,
            )

    with tab2:
        with st.form("create_factory"):
            name = st.text_input("Factory Name")
            expiry = st.date_input("License Expiry", value=dt.date.today() + dt.timedelta(days=365))
            admin_username = st.text_input("Main Admin Username")
            admin_password = st.text_input("Main Admin Temp Password", type="password")
            admin_full_name = st.text_input("Main Admin Full Name")
            if st.form_submit_button("Create Factory + Main Admin"):
                with get_session() as db:
                    factory = Factory(name=name, license_expiry=expiry, is_active=True)
                    db.add(factory)
                    db.flush()
                    seed_defect_codes_for_factory(db, factory.id)
                    admin = User(
                        factory_id=factory.id, username=admin_username, full_name=admin_full_name,
                        role=UserRole.MAIN_ADMIN, password_hash=hash_password(admin_password),
                        must_reset_password=True,
                    )
                    db.add(admin)
                    db.commit()
                    log_audit(st.session_state["user_id"], "create", "factories", factory.id,
                               new_value={"name": name})
                st.success(f"Factory '{name}' created with Main Admin '{admin_username}'. "
                           f"Default defect-code library seeded for all 4 departments.")

    with tab3:
        with get_session() as db:
            factories = db.query(Factory).all()
            factory_snapshots = [
                {"id": f.id, "name": f.name, "license_expiry": f.license_expiry, "is_active": f.is_active}
                for f in factories
            ]
        if factory_snapshots:
            id_to_name = {f["id"]: f["name"] for f in factory_snapshots}
            target_id = st.selectbox("Factory", list(id_to_name.keys()), format_func=lambda i: id_to_name[i])
            target = next(f for f in factory_snapshots if f["id"] == target_id)

            new_expiry = st.date_input("New License Expiry", value=target["license_expiry"] or dt.date.today())
            active = st.checkbox("Active", value=target["is_active"])
            if st.button("Update License"):
                with get_session() as db:
                    f = db.query(Factory).get(target_id)
                    f.license_expiry = new_expiry
                    f.is_active = active
                    db.commit()
                    log_audit(st.session_state["user_id"], "update", "factories", f.id,
                               new_value={"license_expiry": str(new_expiry), "is_active": active})
                st.success("Updated.")

            st.markdown("---")
            st.markdown("**Reset a factory's Main Admin password**")
            with get_session() as db:
                main_admins = db.query(User).filter(
                    User.factory_id == target_id, User.role == UserRole.MAIN_ADMIN
                ).all()
                main_admin_snapshots = [{"id": u.id, "username": u.username} for u in main_admins]
            if main_admin_snapshots:
                id_to_username = {u["id"]: u["username"] for u in main_admin_snapshots}
                admin_user_id = st.selectbox("Main Admin", list(id_to_username.keys()),
                                              format_func=lambda i: id_to_username[i])
                new_pw = st.text_input("New password", type="password", key="super_reset_pw")
                if st.button("Reset Main Admin Password"):
                    with get_session() as db:
                        u = db.query(User).get(admin_user_id)
                        u.password_hash = hash_password(new_pw)
                        u.must_reset_password = True
                        db.commit()
                        log_audit(st.session_state["user_id"], "update", "users", u.id,
                                   new_value={"password_hash": "***"})
                    st.success("Password reset.")
        else:
            st.info("No factories yet — create one in the 'Create Factory' tab.")
