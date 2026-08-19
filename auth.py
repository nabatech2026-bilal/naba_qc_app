"""
auth.py
-------
Login, password hashing, and role-based permission checks for the 4-tier
(+ hidden super tier) hierarchy:

    SUPER_MASTER_ADMIN  - hidden panel, not shown on any factory dashboard.
                           Sets license expiry, resets any factory's master
                           password, activates/deactivates factories.
    MAIN_ADMIN          - full control of one factory: dashboards, reports,
                           all sub-users, defect codes, white-label settings.
    ASSISTANT_ADMIN     - everything MAIN_ADMIN can do EXCEPT deleting the
                           factory itself or demoting a MAIN_ADMIN. Lets the
                           admin delegate user-creation/password-reset work
                           without sharing their own password.
    HALL_MANAGER        - scoped to one hall: can view/reset passwords of
                           inspectors under that hall only.
    FLOOR_INSPECTOR     - mobile data entry only, no admin screens.
"""

import bcrypt
import streamlit as st

from database import get_session, User, UserRole, AuditLog


# ------------------------------------------------------------- Passwords --
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ------------------------------------------------------------------ Login -
def login(username: str, password: str, factory_id: int | None = None) -> User | None:
    """
    Returns the User row on success, else None.
    factory_id=None is only valid for the Super Master Admin, whose account
    is not tied to any single factory.
    """
    with get_session() as db:
        query = db.query(User).filter(User.username == username, User.is_active == True)  # noqa: E712
        if factory_id is not None:
            query = query.filter(User.factory_id == factory_id)
        user = query.first()
        if user and verify_password(password, user.password_hash):
            db.expunge(user)
            return user
    return None


def start_session(user: User):
    st.session_state["user_id"] = user.id
    st.session_state["username"] = user.username
    st.session_state["full_name"] = user.full_name
    st.session_state["role"] = user.role.value
    st.session_state["factory_id"] = user.factory_id
    st.session_state["hall_id"] = user.hall_id
    st.session_state["must_reset_password"] = user.must_reset_password


def logout():
    for key in ["user_id", "username", "full_name", "role", "factory_id", "hall_id", "must_reset_password"]:
        st.session_state.pop(key, None)


def current_role() -> str | None:
    return st.session_state.get("role")


def is_logged_in() -> bool:
    return "user_id" in st.session_state


# ------------------------------------------------------------ Permissions -
# Screens each role is allowed to see. Extend as new pages are added.
ROLE_PERMISSIONS = {
    UserRole.SUPER_MASTER_ADMIN.value: {
        "super_panel", "factory_management", "license_management",
    },
    UserRole.MAIN_ADMIN.value: {
        "dashboard", "data_entry", "user_management", "defect_code_management",
        "white_label_settings", "reports", "audit_log", "import_export",
    },
    UserRole.ASSISTANT_ADMIN.value: {
        "dashboard", "data_entry", "user_management", "defect_code_management",
        "reports", "audit_log", "import_export",
    },
    UserRole.HALL_MANAGER.value: {
        "dashboard", "data_entry", "hall_user_management", "reports", "import_export",
    },
    UserRole.FLOOR_INSPECTOR.value: {
        "data_entry",
    },
}


def can_access(screen: str) -> bool:
    role = current_role()
    if not role:
        return False
    return screen in ROLE_PERMISSIONS.get(role, set())


def require_access(screen: str):
    """Call at the top of a page. Stops rendering with an error if not allowed."""
    if not is_logged_in():
        st.error("Please log in to continue. / براہ کرم جاری رکھنے کے لیے لاگ ان کریں۔")
        st.stop()
    if not can_access(screen):
        st.error("You do not have permission to view this page. / آپ کو اس صفحے تک رسائی کی اجازت نہیں۔")
        st.stop()


def can_manage_user(target_role: str) -> bool:
    """Who is allowed to create/reset-password for whom."""
    actor = current_role()
    hierarchy_order = [
        UserRole.SUPER_MASTER_ADMIN.value,
        UserRole.MAIN_ADMIN.value,
        UserRole.ASSISTANT_ADMIN.value,
        UserRole.HALL_MANAGER.value,
        UserRole.FLOOR_INSPECTOR.value,
    ]
    if actor not in hierarchy_order or target_role not in hierarchy_order:
        return False
    # A role may only manage roles strictly below it in the hierarchy.
    # Assistant admin sits at the same functional level as main admin for
    # user management EXCEPT it cannot manage another main/assistant admin.
    if actor == UserRole.ASSISTANT_ADMIN.value and target_role in (
        UserRole.MAIN_ADMIN.value, UserRole.ASSISTANT_ADMIN.value
    ):
        return False
    return hierarchy_order.index(actor) < hierarchy_order.index(target_role)


# ------------------------------------------------------------------ Audit -
def log_audit(user_id: int, action: str, table_name: str, record_id: int,
              old_value: dict | None = None, new_value: dict | None = None):
    """Write a tamper-trail row. Call this from any edit/delete operation."""
    with get_session() as db:
        db.add(AuditLog(
            user_id=user_id, action=action, table_name=table_name,
            record_id=record_id, old_value=old_value, new_value=new_value,
        ))
