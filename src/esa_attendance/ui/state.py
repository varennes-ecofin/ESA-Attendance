"""Cached Streamlit resources.

This is the only place where Streamlit caching decorators are applied, so the
underlying layers stay free of Streamlit and remain testable. Call
:func:`clear_roster_caches` after any write to the roster files.
"""

from __future__ import annotations

import streamlit as st

from ..data.repository import AttendanceRepository, get_client
from ..roster.models import Course, Student
from ..roster.service import RosterService, build_roster_service

ROSTER_TTL = 300


@st.cache_resource(show_spinner=False)
def get_roster_service() -> RosterService:
    """Return the shared roster service."""
    return build_roster_service()


@st.cache_resource(show_spinner=False)
def get_repository(role: str = "service") -> AttendanceRepository:
    """Return a shared repository bound to the given Supabase role.

    Args:
        role: ``"service"`` for authenticated pages, ``"anon"`` for the public
            check-in page.

    Returns:
        The repository instance.
    """
    return AttendanceRepository(get_client(role))  # type: ignore[arg-type]


@st.cache_data(ttl=ROSTER_TTL, show_spinner=False)
def load_students(academic_year: str) -> list[Student]:
    """Return the students of a year, cached for a few minutes."""
    return get_roster_service().load_students(academic_year)


@st.cache_data(ttl=ROSTER_TTL, show_spinner=False)
def load_courses(academic_year: str) -> list[Course]:
    """Return the courses of a year, cached for a few minutes."""
    return get_roster_service().load_courses(academic_year)


@st.cache_data(ttl=ROSTER_TTL, show_spinner=False)
def current_academic_year() -> str:
    """Return the active academic year from the roster manifest."""
    return get_roster_service().current_academic_year()


def clear_roster_caches() -> None:
    """Invalidate every roster-derived cache after a write."""
    load_students.clear()
    load_courses.clear()
    current_academic_year.clear()
