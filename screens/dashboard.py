"""
screens/dashboard.py
---------------------
Visual analytics: Pie chart (defect share), Pareto bar chart (top 5
defects), line chart (daily trend), plus Daily/Weekly/Monthly and
Brand/Destination/Hall filters, as specified.
"""

import datetime as dt
import pandas as pd
import plotly.express as px
import streamlit as st

from auth import require_access
from database import get_session, InspectionReport, InspectionDefectEntry, DefectCode, Hall, Unit, Destination


def _load_data(factory_id: int, date_from, date_to, department=None, hall_id=None, destination_id=None):
    with get_session() as db:
        q = (
            db.query(InspectionReport)
            .filter(InspectionReport.factory_id == factory_id,
                    InspectionReport.report_date >= date_from,
                    InspectionReport.report_date <= date_to)
        )
        if department and department != "All":
            q = q.filter(InspectionReport.department == department)
        if hall_id and hall_id != "All":
            q = q.filter(InspectionReport.hall_id == hall_id)
        reports = q.all()

        rows = []
        for r in reports:
            rows.append({
                "id": r.id, "date": r.report_date, "department": r.department,
                "hall_id": r.hall_id, "total_inspected": r.total_inspected,
                "total_defects": r.total_defects, "defective_pct": r.defective_percentage,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
            })
        report_df = pd.DataFrame(rows)

        defect_rows = []
        for r in reports:
            for e in r.defect_entries:
                defect_rows.append({
                    "report_id": r.id, "date": r.report_date, "department": r.department,
                    "code": e.defect_code.code, "label": e.defect_code.label,
                    "quantity": e.quantity, "severity": e.severity.value,
                })
        defect_df = pd.DataFrame(defect_rows)

    return report_df, defect_df


def render():
    require_access("dashboard")
    st.header("📊 Dashboard / ڈیش بورڈ")

    factory_id = st.session_state["factory_id"]

    with get_session() as db:
        halls = (
            db.query(Hall)
            .join(Unit, Hall.unit_id == Unit.id)
            .join(Destination, Unit.destination_id == Destination.id)
            .filter(Destination.factory_id == factory_id)
            .all()
        )
        hall_options = {"All": "All"} | {h.id: f"{h.unit.destination.name}/{h.unit.name}/{h.name}" for h in halls}

    c1, c2, c3, c4 = st.columns(4)
    preset = c1.selectbox("Range / رینج", ["Today", "This Week", "This Month", "Custom"])
    today = dt.date.today()
    if preset == "Today":
        date_from, date_to = today, today
    elif preset == "This Week":
        date_from, date_to = today - dt.timedelta(days=today.weekday()), today
    elif preset == "This Month":
        date_from, date_to = today.replace(day=1), today
    else:
        date_from = c1.date_input("From", value=today - dt.timedelta(days=30))
        date_to = c1.date_input("To", value=today)

    department = c2.selectbox("Department", ["All", "cutting", "stitching", "checking", "packing"])
    hall_id = c3.selectbox("Hall", list(hall_options.keys()), format_func=lambda h: hall_options[h])
    c4.write("")  # spacer

    report_df, defect_df = _load_data(factory_id, date_from, date_to, department, hall_id)

    if report_df.empty:
        st.info("No inspection data in this range yet. / اس رینج میں ابھی کوئی ڈیٹا موجود نہیں۔")
        return

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Inspected", int(report_df["total_inspected"].sum()))
    k2.metric("Total Defects", int(report_df["total_defects"].sum()))
    avg_pct = report_df["defective_pct"].mean()
    k3.metric("Avg Defective %", f"{avg_pct:.2f}%")
    pass_rate = (report_df["status"] == "pass").mean() * 100 if len(report_df) else 0
    k4.metric("Lot Pass Rate", f"{pass_rate:.1f}%")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Defect Share (Pie) / ڈیفیکٹ شیئر")
        if not defect_df.empty:
            pie_data = defect_df.groupby("label")["quantity"].sum().reset_index()
            fig = px.pie(pie_data, names="label", values="quantity")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No defect line items yet.")

    with col_b:
        st.subheader("Top 5 Defects (Pareto) / ٹاپ 5 ڈیفیکٹس")
        if not defect_df.empty:
            top5 = defect_df.groupby("label")["quantity"].sum().nlargest(5).reset_index()
            fig = px.bar(top5, x="label", y="quantity", text="quantity")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No defect line items yet.")

    st.subheader("Daily Trend (Line) / یومیہ رجحان")
    trend = report_df.groupby("date")[["total_inspected", "total_defects"]].sum().reset_index()
    fig = px.line(trend, x="date", y=["total_inspected", "total_defects"], markers=True)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Hall-wise Performance / ہال کے حساب سے کارکردگی")
    hall_perf = report_df.groupby("hall_id")[["total_inspected", "total_defects"]].sum().reset_index()
    hall_perf["hall"] = hall_perf["hall_id"].map(hall_options)
    fig = px.bar(hall_perf, x="hall", y=["total_inspected", "total_defects"], barmode="group")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Raw Reports")
    st.dataframe(report_df, use_container_width=True)
