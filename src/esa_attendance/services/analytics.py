"""Assiduity analytics.

Supabase only stores students who showed up, so the denominator -- who was
enrolled -- comes from the roster CSV. This module is pure: it takes the
attendance detail already fetched by the caller and the roster already loaded,
and returns a table. No Supabase call, no Streamlit call, hence testable with
two DataFrames.

Compared with the previous implementation, three things changed. The session
data arrives in one query on the ``attendance_detail`` view instead of chunked
``.in_()`` calls; the level of a student comes from the roster instead of being
guessed from "the first course of that year"; and the set of courses entering
the denominator can be restricted, so a student is no longer penalised for an
elective they were never enrolled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

import pandas as pd

from ..roster.models import Course, Student, normalize_key

RESULT_COLUMNS = [
    "student_id",
    "student_name",
    "sessions_attended",
    "total_sessions",
    "attendance_rate",
    "missed_sessions",
]


@dataclass(frozen=True)
class AssiduityResult:
    """Outcome of an assiduity computation.

    Attributes:
        frame: One row per student, sorted by ascending attendance rate.
        total_sessions: Number of closed sessions in the denominator.
        unmatched: Names present in the attendance records but absent from the
            roster, typically students who left after being recorded.
    """

    frame: pd.DataFrame
    total_sessions: int
    unmatched: tuple[str, ...] = ()


def _session_dates(detail: pd.DataFrame) -> pd.Series:
    """Return the local calendar date of each row's session."""
    parsed = pd.to_datetime(detail["started_at"], format="ISO8601", utc=True)
    return parsed.dt.tz_convert("Europe/Paris").dt.date


def _remap_ids(present: pd.DataFrame, students: Sequence[Student]) -> tuple[pd.DataFrame, list[str]]:
    """Reattach records whose identifier is unknown but whose name matches.

    A student whose identifier changed between two roster imports would
    otherwise appear as absent from every session. Matching falls back on the
    normalised name.

    Args:
        present: Attendance rows with non-null ``student_id``.
        students: Roster of the level under study.

    Returns:
        The rows with corrected identifiers, and the names that could not be
        matched at all.
    """
    known_ids = {s.student_id for s in students}
    by_name = {normalize_key(s.name): s.student_id for s in students}

    present = present.copy()
    unknown = ~present["student_id"].isin(known_ids)
    if not unknown.any():
        return present, []

    fallback = present.loc[unknown, "student_name"].map(
        lambda name: by_name.get(normalize_key(str(name)), "")
    )
    present.loc[unknown, "student_id"] = fallback.where(fallback != "", present.loc[unknown, "student_id"])

    still_unknown = ~present["student_id"].isin(known_ids)
    unmatched = sorted(set(present.loc[still_unknown, "student_name"].astype(str)))
    return present.loc[~still_unknown], unmatched


def compute_assiduity(
    detail: pd.DataFrame,
    students: Sequence[Student],
    courses: Sequence[Course],
    level: str,
    date_from: date,
    date_to: date,
    course_codes: Sequence[str] | None = None,
    top_n: int | None = None,
) -> AssiduityResult:
    """Compute attendance rates for the students of one level.

    The rate of a student is ``sessions_attended / total_sessions``, where the
    denominator counts the distinct closed sessions held in the period for the
    selected courses.

    Args:
        detail: Rows of the ``attendance_detail`` view for one academic year.
        students: Full roster, all levels; filtered internally.
        courses: Course catalogue, used to map a course code to a level.
        level: ``"M1"`` or ``"M2"``.
        date_from: First day of the window, inclusive.
        date_to: Last day of the window, inclusive.
        course_codes: Restrict the denominator to these courses; ``None`` means
            every course of the level.
        top_n: Keep only the ``top_n`` least assiduous students; ``None`` keeps
            everyone.

    Returns:
        The corresponding :class:`AssiduityResult`.
    """
    roster = [s for s in students if s.level == level]
    empty = pd.DataFrame(columns=RESULT_COLUMNS)

    if not roster:
        return AssiduityResult(frame=empty, total_sessions=0)

    selected = {c.code for c in courses if c.level == level}
    if course_codes is not None:
        selected &= set(course_codes)

    if detail.empty or not selected:
        return AssiduityResult(frame=empty, total_sessions=0)

    scoped = detail[detail["course_code"].isin(selected)].copy()
    if scoped.empty:
        return AssiduityResult(frame=empty, total_sessions=0)

    scoped["session_date"] = _session_dates(scoped)
    scoped = scoped[
        (scoped["session_date"] >= date_from) & (scoped["session_date"] <= date_to)
    ]

    total_sessions = int(scoped["session_id"].nunique())
    if total_sessions == 0:
        return AssiduityResult(frame=empty, total_sessions=0)

    present = scoped.dropna(subset=["student_id"])
    unmatched: list[str] = []
    if not present.empty:
        present, unmatched = _remap_ids(present, roster)
        present = present.drop_duplicates(subset=["session_id", "student_id"])

    attended = (
        present.groupby("student_id").size().rename("sessions_attended")
        if not present.empty
        else pd.Series(dtype=int, name="sessions_attended")
    )

    result = pd.DataFrame(
        [{"student_id": s.student_id, "student_name": s.name} for s in roster]
    )
    result = (
        result.set_index("student_id")
        .join(attended)
        .fillna({"sessions_attended": 0})
        .reset_index()
    )
    result["sessions_attended"] = result["sessions_attended"].astype(int)
    result["total_sessions"] = total_sessions
    result["attendance_rate"] = (result["sessions_attended"] / total_sessions).round(4)
    result["missed_sessions"] = total_sessions - result["sessions_attended"]

    result = result.sort_values(
        ["attendance_rate", "student_name"], ascending=[True, True]
    ).reset_index(drop=True)
    if top_n is not None:
        result = result.head(top_n)

    return AssiduityResult(
        frame=result[RESULT_COLUMNS],
        total_sessions=total_sessions,
        unmatched=tuple(unmatched),
    )
