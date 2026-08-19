"""
screens/import_export.py
--------------------------
Dedicated screen for the mandatory Import / Export feature.

Export tab: pick a date range + department, download an .xlsx with all
matching reports (defect quantities included as columns).

Import tab: download a blank template (pre-filled with the factory's own
defect-code columns for the chosen department), fill it in Excel, upload
it back, and the app bulk-creates the reports. Any row that fails
validation is skipped and listed so nothing silently disappears.
"""

import datetime as dt
import streamlit as st

from auth import require_access
from utils.import_export import export_reports_to_excel, build_import_template, import_reports_from_file

DEPARTMENTS = ["cutting", "stitching", "checking", "packing"]


def render():
    require_access("import_export")  # Hall Manager and above — not Floor Inspector
    st.header("🔁 Import / Export / ڈیٹا امپورٹ ایکسپورٹ")

    factory_id = st.session_state["factory_id"]
    user_id = st.session_state["user_id"]

    tab_export, tab_import = st.tabs(["⬇️ Export", "⬆️ Import"])

    with tab_export:
        st.subheader("Export existing reports to Excel")
        c1, c2, c3 = st.columns(3)
        date_from = c1.date_input("From", value=dt.date.today() - dt.timedelta(days=30), key="exp_from")
        date_to = c2.date_input("To", value=dt.date.today(), key="exp_to")
        department = c3.selectbox("Department", ["All"] + DEPARTMENTS, key="exp_dept")

        if st.button("Generate Excel Export"):
            data = export_reports_to_excel(factory_id, date_from, date_to, department)
            st.download_button(
                "⬇️ Download Excel", data=data,
                file_name=f"qc_reports_{date_from}_{date_to}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    with tab_import:
        st.subheader("Bulk import from Excel/CSV")
        department_i = st.selectbox("Department", DEPARTMENTS, key="imp_dept")

        st.markdown("**Step 1 — Download the template** (already has your defect-code columns for this department)")
        template_bytes = build_import_template(factory_id, department_i)
        st.download_button(
            "⬇️ Download Blank Template", data=template_bytes,
            file_name=f"import_template_{department_i}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.markdown("**Step 2 — Fill it in Excel, then upload it here**")
        uploaded = st.file_uploader("Upload filled template", type=["xlsx", "csv"], key="imp_upload")

        if uploaded is not None and st.button("Import Now"):
            success_count, errors = import_reports_from_file(factory_id, department_i, uploaded, user_id)
            st.success(f"✅ Imported {success_count} report(s).")
            if errors:
                st.warning(f"⚠️ {len(errors)} row(s) skipped:")
                for e in errors:
                    st.write(f"- {e}")
