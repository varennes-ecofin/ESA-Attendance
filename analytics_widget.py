"""
Streamlit analytics widget for the ESA teacher dashboard.

Drop-in section to add inside teacher_dashboard() in app.py, for example
after the "Courses Statistics" block.

Usage in app.py:
    from analytics_widget import render_assiduity_panel
    render_assiduity_panel()
"""

from datetime import date

import streamlit as st

from utils.analytics import least_assiduous_students


def render_assiduity_panel() -> None:
    """
    Render the least-assiduous-students panel inside the Streamlit dashboard.

    Provides year selector, date range pickers, N selector, and a results
    table with a colour-coded attendance rate column.
    """
    st.markdown("---")
    st.subheader("📉 Least Assiduous Students")

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    col_year, col_n, col_from, col_to = st.columns([1, 1, 2, 2])

    with col_year:
        year = st.selectbox("Year", options=["M1", "M2"], key="assiduity_year")

    with col_n:
        top_n = st.number_input(
            "Show N students", min_value=1, max_value=30, value=5,
            key="assiduity_n",
        )

    with col_from:
        date_from = st.date_input(
            "From",
            value=date(date.today().year, 1, 1),
            key="assiduity_from",
        )

    with col_to:
        date_to = st.date_input(
            "To",
            value=date.today(),
            key="assiduity_to",
        )

    if date_from > date_to:
        st.warning("⚠️ 'From' date must be before 'To' date.")
        return

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    with st.spinner("Fetching attendance data…"):
        df = least_assiduous_students(
            year=year,
            date_from=date_from,
            date_to=date_to,
            top_n=int(top_n),
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    if df.empty:
        st.info("No sessions found for this period.")
        return

    total_sessions = int(df["total_sessions"].iloc[0])
    st.caption(
        f"Period: {date_from} → {date_to} | "
        f"Total closed sessions for {year}: **{total_sessions}**"
    )

    # Rename columns for display
    df_display = df.rename(columns={
        "student_name":     "Student",
        "sessions_attended":"Attended",
        "total_sessions":   "Total Sessions",
        "missed_sessions":  "Missed",
        "attendance_rate":  "Rate",
    }).drop(columns=["student_id"])

    # Format rate as percentage string for readability
    df_display["Rate"] = df_display["Rate"].apply(lambda x: f"{x:.1%}")

    st.dataframe(
        df_display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Rate": st.column_config.TextColumn("Attendance Rate"),
            "Attended": st.column_config.NumberColumn("✅ Attended"),
            "Missed":   st.column_config.NumberColumn("❌ Missed"),
        },
    )

    # Optional CSV export
    csv = df.to_csv(index=False)
    st.download_button(
        label="💾 Export CSV",
        data=csv,
        file_name=f"assiduity_{year}_{date_from}_{date_to}.csv",
        mime="text/csv",
        key="assiduity_export",
    )
