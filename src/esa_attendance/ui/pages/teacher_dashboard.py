"""Teacher dashboard: open a session, show the QR code, follow the check-ins.

The live list is refreshed by ``st.fragment(run_every=5)``. The previous version
looped on ``time.sleep(5)`` followed by ``st.rerun()``, which re-executed the
whole script -- sidebar queries included -- every five seconds; only the
attendance block needs refreshing.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
import qrcode
import streamlit as st

from ...config import get_settings
from ...services.mailer import MailError, send_attendance_report
from ..login import require_role
from ..state import current_academic_year, get_repository, load_courses, load_students

SESSION_KEY = "active_session_id"


# ---------------------------------------------------------------------------
# Live block, refreshed on its own
# ---------------------------------------------------------------------------

@st.fragment(run_every=5)
def _live_attendance(session_id: str, expected: int) -> None:
    """Render the attendance list, re-running every five seconds.

    Args:
        session_id: Session being followed.
        expected: Number of enrolled students, used for the progress bar.
    """
    frame = get_repository("service").session_attendance_frame(session_id)

    if frame.empty:
        st.info("En attente des premiers émargements…", icon="⏳")
        return

    st.dataframe(frame, hide_index=True, width="stretch")
    ratio = min(len(frame) / expected, 1.0) if expected else 0.0
    st.progress(ratio)
    st.caption(f"{len(frame)} / {expected} étudiants présents ({ratio:.0%})")


# ---------------------------------------------------------------------------
# Session control
# ---------------------------------------------------------------------------

def _qr_png(url: str) -> bytes:
    """Return a PNG QR code encoding ``url``."""
    code = qrcode.QRCode(version=1, box_size=10, border=4)
    code.add_data(url)
    code.make(fit=True)
    buffer = BytesIO()
    code.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def _start_session(course_code: str, username: str, academic_year: str) -> str:
    """Open a session, closing the teacher's own stale ones first.

    A session left open keeps accepting check-ins from an old QR code, so any
    session still active for this teacher is closed before a new one starts.

    Args:
        course_code: Course of the new session.
        username: Teacher opening the session.
        academic_year: Active academic year.

    Returns:
        The identifier of the newly created session.
    """
    repository = get_repository("service")
    for previous in repository.teacher_sessions(username, limit=20):
        if previous.get("status") == "active":
            repository.close_session(previous["session_id"])

    session_id = f"{course_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    repository.create_session(session_id, course_code, username, academic_year)
    return session_id


def _render_sidebar(username: str, academic_year: str) -> str | None:
    """Render the sidebar and return the selected course code."""
    with st.sidebar:
        st.header("Session d'appel")
        st.caption(f"Année active : {academic_year}")

        courses = [c for c in load_courses(academic_year) if c.active]
        if not courses:
            roster = get_settings().roster
            source = (
                f"dossier local « {roster.local_dir} »"
                if roster.backend == "local"
                else f"bucket Supabase « {roster.bucket} »"
            )
            st.error(
                f"Aucun cours au catalogue pour {academic_year}.\n\n"
                f"Source consultée : {source}, fichier "
                f"`{academic_year}/courses.csv`."
            )
            return None

        labels = {c.code: f"{c.name} ({c.level})" for c in courses}
        selected = st.selectbox(
            "Cours",
            options=[c.code for c in courses],
            format_func=lambda code: labels[code],
        )

        with st.expander("Sessions récentes"):
            recent = get_repository("service").teacher_sessions(username, limit=5)
            if not recent:
                st.caption("Aucune session.")
            for entry in recent:
                marker = "🟢" if entry["status"] == "active" else "⚪"
                st.write(f"{marker} {entry['course_code']} — {entry['started_at'][:10]}")

    return selected


# ---------------------------------------------------------------------------
# Statistics shown between sessions
# ---------------------------------------------------------------------------

def _render_statistics(academic_year: str) -> None:
    """Render per-course statistics for the active year, in one query."""
    st.subheader("Statistiques de l'année")

    stats = get_repository("service").course_stats(academic_year)
    if stats.empty:
        st.info("Aucune session fermée pour cette année.")
        return

    courses = {c.code: c for c in load_courses(academic_year)}
    students = load_students(academic_year)
    headcount = {
        level: sum(1 for s in students if s.level == level) for level in ("M1", "M2")
    }

    rows = []
    for entry in stats.to_dict("records"):
        course = courses.get(entry["course_code"])
        enrolled = headcount.get(course.level, 0) if course else 0
        average = float(entry["avg_per_session"] or 0)
        rows.append(
            {
                "Code": entry["course_code"],
                "Cours": course.name if course else "(hors catalogue)",
                "Niveau": course.level if course else "—",
                "Séances": int(entry["num_sessions"]),
                "Présents/séance": round(average, 1),
                "Taux": f"{average / enrolled:.0%}" if enrolled else "—",
            }
        )

    frame = pd.DataFrame(rows).sort_values(["Niveau", "Code"])
    st.dataframe(frame, hide_index=True, width="stretch")
    st.caption(
        "Séances fermées uniquement. Une session laissée ouverte n'est comptée "
        "nulle part tant qu'elle ne l'est pas."
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _render_actions(session_id: str, course_label: str) -> None:
    """Render the export and e-mail actions for the running session."""
    repository = get_repository("service")
    records = repository.session_records(session_id)
    if not records:
        return

    st.markdown("---")
    left, right = st.columns(2)

    with left:
        csv = pd.DataFrame(records).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "💾 Télécharger le CSV",
            data=csv,
            file_name=f"presences_{session_id}.csv",
            mime="text/csv",
        )

    with right:
        if st.button("📧 Envoyer au secrétariat"):
            settings = get_settings()
            if settings.email is None:
                st.error("Aucune configuration SMTP dans les secrets.", icon="🚫")
                return
            try:
                targets = send_attendance_report(
                    settings.email,
                    course_label,
                    datetime.now().strftime("%d/%m/%Y"),
                    records,
                )
            except MailError as exc:
                st.error(str(exc), icon="🚫")
            else:
                st.success(f"Envoyé à {', '.join(targets)}.", icon="✅")


def render() -> None:
    """Render the teacher dashboard."""
    user = require_role()
    academic_year = current_academic_year()

    st.title("Tableau de bord")

    course_code = _render_sidebar(user.username, academic_year)
    if course_code is None:
        st.stop()

    courses = {c.code: c for c in load_courses(academic_year)}
    course = courses[course_code]
    course_label = f"{course.name} ({course.level})"
    enrolled = sum(1 for s in load_students(academic_year) if s.level == course.level)

    session_id = st.session_state.get(SESSION_KEY)
    left, right = st.columns([1, 2])

    with left:
        st.subheader("QR code")
        if session_id is None:
            if st.button("🟢 Ouvrir la session", type="primary", width="stretch"):
                st.session_state[SESSION_KEY] = _start_session(
                    course_code, user.username, academic_year
                )
                st.rerun()
            st.info("Ouvrez une session pour afficher le QR code.")
        else:
            if st.button("🔴 Fermer la session", width="stretch"):
                get_repository("service").close_session(session_id)
                st.session_state.pop(SESSION_KEY, None)
                st.success("Session fermée.", icon="✅")
                st.rerun()

            base_url = get_settings().base_url or "http://localhost:8501"
            url = f"{base_url}/?session={session_id}&mode=student"
            st.image(_qr_png(url))
            st.caption("Les étudiants scannent ce code pour émarger.")
            st.link_button("Ouvrir la vue étudiant", url)

    with right:
        st.subheader("Émargements en direct")
        if session_id is None:
            _render_statistics(academic_year)
        else:
            _live_attendance(session_id, enrolled)
            _render_actions(session_id, course_label)
