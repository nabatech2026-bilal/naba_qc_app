"""
app.py
------
Entry point. Handles:
  1. Splash screen (NABA Tech logo/intro video, shown once per browser
     session before login — matches "Intro Splash Screen" spec item).
  2. Login (factory selection + username/password; Super Master Admin logs
     in without picking a factory).
  3. Forced password reset on first login (must_reset_password flag).
  4. Role-based sidebar navigation into the screens/ modules.

Run with:  streamlit run app.py
First-time setup: run `python seed.py` once to create the Super Master
Admin account and initialize the database tables.
"""

import os
import streamlit as st

from database import init_db, get_session, Factory
from auth import login, start_session, logout, is_logged_in, current_role, hash_password
from database import User

APP_NAME = os.getenv("APP_NAME", "NABA Tech QC")
CREDIT_LINE = os.getenv("CREDIT_LINE", "Powered by NABA Tech By Kaleem Ullah Sharif")

st.set_page_config(page_title=APP_NAME, page_icon="🧵", layout="wide")


def _footer():
    st.markdown(
        f"<hr style='margin-top:2rem;margin-bottom:0.5rem'>"
        f"<div style='text-align:center;color:gray;font-size:0.8rem'>{CREDIT_LINE}</div>",
        unsafe_allow_html=True,
    )


def _splash():
    """Shown once per browser session before the login form."""
    if st.session_state.get("splash_shown"):
        return
    logo_path = "assets/naba_logo.png"
    video_path = "assets/naba_intro.mp4"

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Logo takes the place of the "NABA Tech QC" text title.
        if os.path.exists(logo_path):
            st.image(logo_path, use_container_width=True)
        else:
            st.markdown(f"<h1 style='text-align:center'>{APP_NAME}</h1>", unsafe_allow_html=True)

        # Only the intro video plays here — autoplay (muted, since browsers
        # block unmuted autoplay) so it starts on its own.
        if os.path.exists(video_path):
            st.video(video_path, autoplay=True, muted=True)
    st.markdown(f"<p style='text-align:center;color:gray'>{CREDIT_LINE}</p>", unsafe_allow_html=True)
    if st.button("Continue to Login ➜", use_container_width=True):
        st.session_state["splash_shown"] = True
        st.rerun()
    st.stop()


def _login_screen():
    st.markdown(f"<h2 style='text-align:center'>🔐 {APP_NAME} — Login</h2>", unsafe_allow_html=True)

    login_mode = st.radio("Login as", ["Factory User", "Super Master Admin"], horizontal=True)

    if login_mode == "Factory User":
        with get_session() as db:
            factories = db.query(Factory).filter(Factory.is_active == True).all()  # noqa: E712
            factory_options = {f.id: f.name for f in factories}
        if not factory_options:
            st.warning("No active factories yet. Ask the Super Master Admin to set one up.")
            return
        factory_id = st.selectbox("Factory", list(factory_options.keys()), format_func=lambda i: factory_options[i])
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Log In", use_container_width=True):
            user = login(username, password, factory_id=factory_id)
            if user:
                start_session(user)
                st.rerun()
            else:
                st.error("Invalid username or password. / غلط یوزر نیم یا پاس ورڈ۔")
    else:
        username = st.text_input("Super Admin Username")
        password = st.text_input("Password", type="password")
        if st.button("Log In", use_container_width=True):
            user = login(username, password, factory_id=None)
            if user and user.role.value == "super_master_admin":
                start_session(user)
                st.rerun()
            else:
                st.error("Invalid credentials.")

    _footer()


def _force_password_reset():
    st.warning("🔑 You must set a new password before continuing. / جاری رکھنے سے پہلے نیا پاس ورڈ سیٹ کریں۔")
    new_pw = st.text_input("New Password", type="password")
    confirm_pw = st.text_input("Confirm New Password", type="password")
    if st.button("Update Password"):
        if len(new_pw) < 6:
            st.error("Password must be at least 6 characters.")
        elif new_pw != confirm_pw:
            st.error("Passwords do not match.")
        else:
            with get_session() as db:
                u = db.query(User).get(st.session_state["user_id"])
                u.password_hash = hash_password(new_pw)
                u.must_reset_password = False
                db.commit()
            st.session_state["must_reset_password"] = False
            st.success("Password updated.")
            st.rerun()
    st.stop()


def _main_app():
    role = current_role()
    st.sidebar.markdown(f"### {APP_NAME}")
    st.sidebar.write(f"👤 {st.session_state.get('full_name')}")
    st.sidebar.caption(f"Role: {role}")

    nav_options = []
    if role == "super_master_admin":
        nav_options = ["Super Panel"]
    else:
        nav_options.append("Dashboard")
        nav_options.append("Data Entry")
        if role in ("main_admin", "assistant_admin", "hall_manager"):
            nav_options.append("Import / Export")
            nav_options.append("Admin")

    choice = st.sidebar.radio("Navigate", nav_options)

    if st.sidebar.button("🚪 Log Out"):
        logout()
        st.rerun()

    if choice == "Super Panel":
        from screens import super_admin
        super_admin.render()
    elif choice == "Dashboard":
        from screens import dashboard
        dashboard.render()
    elif choice == "Data Entry":
        from screens import data_entry
        data_entry.render()
    elif choice == "Import / Export":
        from screens import import_export
        import_export.render()
    elif choice == "Admin":
        from screens import admin
        admin.render()

    _footer()


def main():
    init_db()

    if not is_logged_in():
        _splash()
        _login_screen()
        return

    if st.session_state.get("must_reset_password"):
        _force_password_reset()
        return

    _main_app()


if __name__ == "__main__":
    main()
