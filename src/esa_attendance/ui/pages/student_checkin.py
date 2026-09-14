"""Public student check-in page.

No authentication: the only credential is the session identifier carried by the
QR code. Two changes with respect to the previous version. Presence is recorded
through the ``check_in`` RPC, which validates the session and rejects duplicates
server-side -- the page never reads ``attendance_records``. And the roster shown
is the one of the session's own academic year, not the year currently active, so
a session opened before a rollover still lists the right students.
"""

from __future__ import annotations

import streamlit as st

from ..login import LOGO_URL
from ..state import get_repository, load_courses, load_students

CHECKED_IN_KEY = "checkin_done"


def _header() -> None:
    """Render the ESA banner and the page title."""
    st.markdown(
        f"<div style='text-align:center;padding:0.5rem 0'>"
        f"<img src='{LOGO_URL}' style='max-width:280px;width:100%;height:auto'></div>",
        unsafe_allow_html=True,
    )
    st.title("Appel — émargement")


def _confirmation(student_name: str, course_label: str) -> None:
    """Render the post-check-in confirmation and stop the script."""
    st.success("Votre présence est enregistrée.", icon="✅")
    st.markdown(
        f"- **Nom :** {student_name}\n"
        f"- **Cours :** {course_label}\n\n"
        "Vous pouvez fermer cette page."
    )
    st.stop()


def render(session_id: str | None = None) -> None:
    """Render the check-in page.

    Args:
        session_id: Session identifier read from the query string.
    """
    _header()

    if not session_id:
        st.error("Lien invalide. Scannez à nouveau le QR code affiché en cours.", icon="🚫")
        st.stop()

    repository = get_repository("anon")
    session = repository.get_session(session_id)

    if session is None or session.get("status") != "active":
        st.error("Cette session d'appel est fermée ou n'existe pas.", icon="🚫")
        st.info("Demandez à votre enseignant d'ouvrir une nouvelle session.")
        st.stop()

    academic_year = session.get("academic_year", "")
    course_code = session.get("course_code", "")

    courses = {c.code: c for c in load_courses(academic_year)}
    course = courses.get(course_code)
    if course is None:
        st.error(
            f"Le cours {course_code} n'est pas au catalogue de {academic_year}. "
            "Signalez-le à votre enseignant.",
            icon="🚫",
        )
        st.stop()

    st.info(f"**{course.name}** — {course.level}", icon="📚")

    done = st.session_state.get(CHECKED_IN_KEY)
    if isinstance(done, dict) and done.get("session_id") == session_id:
        _confirmation(done["student_name"], course.name)

    students = [s for s in load_students(academic_year) if s.level == course.level]
    if not students:
        st.error(
            f"Aucune liste d'étudiants pour {course.level} en {academic_year}.", icon="🚫"
        )
        st.stop()

    st.markdown("### Sélectionnez votre nom")
    query = st.text_input("Rechercher", placeholder="Tapez les premières lettres…")
    shortlist = (
        [s for s in students if query.lower() in s.name.lower()] if query else students
    )

    if not shortlist:
        st.warning("Aucun nom ne correspond à cette recherche.")
        st.stop()

    chosen_name = st.radio(
        "Votre nom",
        options=[s.name for s in shortlist],
        key="student_choice",
        label_visibility="collapsed",
    )
    student = next((s for s in shortlist if s.name == chosen_name), None)
    if student is None:
        st.stop()

    st.markdown("---")
    st.markdown(f"Nom sélectionné : **{student.name}**")

    if st.button("Confirmer ma présence", type="primary", width="stretch"):
        result = repository.check_in(session_id, student.student_id, student.name)
        if result.ok:
            st.session_state[CHECKED_IN_KEY] = {
                "session_id": session_id,
                "student_name": student.name,
            }
            st.rerun()
        else:
            st.error(result.message, icon="🚫")
