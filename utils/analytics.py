"""
Analytics module for ESA Attendance System.

Computes attendance statistics by joining Supabase records (who showed up)
with the local student roster (who was enrolled), since Supabase only stores
presence data, not the full enrollment list.
"""

from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

from utils.courses import COURSES, get_students
from utils.database import get_service_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _m1_course_codes() -> list[str]:
    """Return all M1 course codes (excluding maintenance pseudo-courses)."""
    return [
        code for code, info in COURSES.items()
        if info["year"] == "M1"
    ]


def _fetch_sessions(
    db,
    course_codes: list[str],
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """
    Fetch closed attendance sessions for the given courses and date range.

    Args:
        db: AttendanceDatabase instance.
        course_codes: List of course codes to filter.
        date_from: Start date (inclusive).
        date_to: End date (inclusive).

    Returns:
        DataFrame with columns [session_id, course_code, started_at].
    """
    result = (
        db.supabase.table("attendance_sessions")
        .select("session_id, course_code, started_at")
        .in_("course_code", course_codes)
        .gte("started_at", datetime.combine(date_from, datetime.min.time()).isoformat())
        .lte("started_at", datetime.combine(date_to, datetime.max.time()).isoformat())
        .eq("status", "closed")        # ignore active / phantom sessions
        .execute()
    )
    if not result.data:
        return pd.DataFrame(columns=["session_id", "course_code", "started_at"])
    return pd.DataFrame(result.data)


def _fetch_attendance(db, session_ids: list[str]) -> pd.DataFrame:
    """
    Fetch all attendance records for a list of session IDs.

    Supabase REST has a URL-length limit; we chunk large lists to be safe.

    Args:
        db: AttendanceDatabase instance.
        session_ids: List of session UUIDs/strings.

    Returns:
        DataFrame with columns [session_id, student_id, student_name].
    """
    CHUNK = 200  # safe chunk size for .in_() filters
    rows: list[dict] = []

    for i in range(0, len(session_ids), CHUNK):
        chunk = session_ids[i : i + CHUNK]
        res = (
            db.supabase.table("attendance_records")
            .select("session_id, student_id, student_name")
            .in_("session_id", chunk)
            .execute()
        )
        if res.data:
            rows.extend(res.data)

    if not rows:
        return pd.DataFrame(columns=["session_id", "student_id", "student_name"])
    return pd.DataFrame(rows)


def _build_roster(year: str) -> pd.DataFrame:
    """
    Build a DataFrame of enrolled students for a given year from courses.py.

    Args:
        year: "M1" or "M2".

    Returns:
        DataFrame with columns [student_id, student_name].
    """
    students = get_students(
        next(
            code for code, info in COURSES.items()
            if info["year"] == year
        )
    )
    return pd.DataFrame(
        [{"student_id": s["id"], "student_name": s["name"]} for s in students]
    )


# ---------------------------------------------------------------------------
# Main analytics function
# ---------------------------------------------------------------------------

def least_assiduous_students(
    year: str = "M1",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Return the N least assiduous students for a given year and date range.

    The attendance rate for a student is defined as:

        rate = sessions_attended / total_sessions_held

    where total_sessions_held counts only closed sessions in the period for
    all courses the student is enrolled in (i.e. all courses of their year).

    Because Supabase only stores *present* students, the full roster is
    sourced from the local courses.py file and cross-joined against the
    session data.

    Args:
        year: "M1" or "M2".
        date_from: Start of the analysis window (default: January 1st of
            the current year).
        date_to: End of the analysis window (default: today).
        top_n: Number of students to return (least assiduous first).

    Returns:
        DataFrame with columns:
            student_id, student_name,
            sessions_attended, total_sessions, attendance_rate (0-1),
            missed_sessions.
        Sorted ascending by attendance_rate.
    """
    if date_from is None:
        date_from = date(date.today().year, 1, 1)
    if date_to is None:
        date_to = date.today()

    db = get_service_db()

    # ------------------------------------------------------------------
    # 1. Retrieve all relevant sessions from Supabase
    # ------------------------------------------------------------------
    course_codes = _m1_course_codes() if year == "M1" else [
        code for code, info in COURSES.items() if info["year"] == year
    ]

    df_sessions = _fetch_sessions(db, course_codes, date_from, date_to)

    if df_sessions.empty:
        return pd.DataFrame(columns=[
            "student_id", "student_name",
            "sessions_attended", "total_sessions",
            "attendance_rate", "missed_sessions",
        ])

    total_sessions_held = df_sessions["session_id"].nunique()
    session_ids = df_sessions["session_id"].tolist()

    # ------------------------------------------------------------------
    # 2. Retrieve attendance records for those sessions
    # ------------------------------------------------------------------
    df_attendance = _fetch_attendance(db, session_ids)

    # ------------------------------------------------------------------
    # 3. Load full student roster (local source)
    # ------------------------------------------------------------------
    df_roster = _build_roster(year)

    # ------------------------------------------------------------------
    # 4. Count attended sessions per student
    # ------------------------------------------------------------------
    if df_attendance.empty:
        attended_counts = pd.Series([], dtype=int, name="sessions_attended")
        attended_counts.index.name = "student_id"
    else:
        attended_counts = (
            df_attendance
            .drop_duplicates(subset=["session_id", "student_id"])
            .groupby("student_id")
            .size()
            .rename("sessions_attended")
        )

    # ------------------------------------------------------------------
    # 5. Left-join roster with attendance counts
    #    Students with zero attendance will get NaN → fill with 0
    # ------------------------------------------------------------------
    df_result = (
        df_roster
        .set_index("student_id")
        .join(attended_counts, how="left")
        .fillna({"sessions_attended": 0})
        .reset_index()
    )
    df_result["sessions_attended"] = df_result["sessions_attended"].astype(int)
    df_result["total_sessions"] = total_sessions_held
    df_result["attendance_rate"] = (
        df_result["sessions_attended"] / total_sessions_held
    ).round(4)
    df_result["missed_sessions"] = (
        total_sessions_held - df_result["sessions_attended"]
    )

    # ------------------------------------------------------------------
    # 6. Return top_n least assiduous
    # ------------------------------------------------------------------
    return (
        df_result
        .sort_values("attendance_rate", ascending=True)
        .head(top_n)
        .reset_index(drop=True)
    )
