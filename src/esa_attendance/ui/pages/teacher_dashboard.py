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
REPORT_KEY = "last_report"


# ---------------------------------------------------------------------------
# Live block, refreshed on its own
# ---------------------------------------------------------------------------

@st.fragment(run_every=5)
def _live_attendance(session_id: str, expected: int) -> None:
    """Render the attendance list and its export, re-running every five seconds.

    The download button lives inside the fragment on purpose. Placed after it,
    it would be drawn once during the full script run -- when nobody has checked
    in yet -- and never redrawn, since a fragment rerun does not re-evaluate the
    code around it.

    Args:
        session_id: Session being followed.
        expected: Number of enrolled students, used for the progress bar.
    """
    records = get_repository("service").session_records(session_id)

    if not records:
        st.info("En attente des premiers émargements…", icon="⏳")
        return

    frame = pd.DataFrame(
        [
            {
                "Étudiant": record["student_name"],
                "Heure": datetime.fromisoformat(
                    record["checked_in_at"].replace("Z", "+00:00")
                )
                .astimezone()
                .strftime("%H:%M:%S"),
            }
            for record in records
        ]
    )
    st.dataframe(frame, hide_index=True, width="stretch")

    ratio = min(len(records) / expected, 1.0) if expected else 0.0
    st.progress(ratio)
    st.caption(f"{len(records)} / {expected} étudiants présents ({ratio:.0%})")

    st.download_button(
        "💾 Télécharger le CSV",
        data=pd.DataFrame(records).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"presences_{session_id}.csv",
        mime="text/csv",
        key="download_live",
    )
    st.caption(
        "La feuille de présence est envoyée au secrétariat à la fermeture de la séance."
    )


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

def _close_and_report(session_id: str, course_label: str) -> dict:
    """Close a session and send the attendance report to the registrar.

    Sending is a consequence of closing rather than a separate button: in
    practice nobody clicked the button, so the report was never sent. The
    records are read before closing and kept in the returned payload, so a
    failed send can still be downloaded or retried.

    Args:
        session_id: Session being closed.
        course_label: Course name shown in the message.

    Returns:
        A payload describing what happened, stored in the session state.
    """
    repository = get_repository("service")
    records = repository.session_records(session_id)
    repository.close_session(session_id)

    payload: dict = {
        "session_id": session_id,
        "course_label": course_label,
        "date": datetime.now().strftime("%d/%m/%Y"),
        "records": records,
        "sent_to": [],
        "error": "",
    }

    if not records:
        payload["error"] = "Aucun émargement : rien n'a été envoyé."
        return payload

    settings = get_settings()
    if settings.email is None:
        payload["error"] = "Aucune configuration SMTP dans les secrets."
        return payload

    try:
        payload["sent_to"] = send_attendance_report(
            settings.email, course_label, payload["date"], records
        )
    except MailError as exc:
        payload["error"] = str(exc)

    return payload


def _render_report_panel() -> None:
    """Render the outcome of the last closed session."""
    payload = st.session_state.get(REPORT_KEY)
    if not isinstance(payload, dict):
        return

    records = payload.get("records") or []
    st.markdown(f"#### Séance close — {payload['course_label']}")

    if payload["sent_to"]:
        st.success(
            f"{len(records)} présences envoyées à {', '.join(payload['sent_to'])}.",
            icon="✅",
        )
    elif payload["error"]:
        st.error(payload["error"], icon="🚫")

    if records:
        csv = pd.DataFrame(records).to_csv(index=False).encode("utf-8-sig")
        left, right = st.columns(2)
        with left:
            st.download_button(
                "💾 Télécharger le CSV",
                data=csv,
                file_name=f"presences_{payload['session_id']}.csv",
                mime="text/csv",
                key="download_closed",
            )
        with right:
            if payload["error"] and st.button("📧 Réessayer l'envoi"):
                settings = get_settings()
                if settings.email is None:
                    st.error("Aucune configuration SMTP dans les secrets.", icon="🚫")
                else:
                    try:
                        payload["sent_to"] = send_attendance_report(
                            settings.email,
                            payload["course_label"],
                            payload["date"],
                            records,
                        )
                        payload["error"] = ""
                    except MailError as exc:
                        payload["error"] = str(exc)
                    st.session_state[REPORT_KEY] = payload
                    st.rerun()

    if st.button("Masquer ce récapitulatif", key="dismiss_report"):
        st.session_state.pop(REPORT_KEY, None)
        st.rerun()

    st.markdown("---")


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
            if st.button(
                "🔴 Fermer la séance et envoyer", type="primary", width="stretch"
            ):
                with st.spinner("Fermeture et envoi…"):
                    st.session_state[REPORT_KEY] = _close_and_report(
                        session_id, course_label
                    )
                st.session_state.pop(SESSION_KEY, None)
                st.rerun()

            configured_url = get_settings().base_url
            if not configured_url:
                st.error(
                    "`base_url` est absent des secrets : le QR code ci-dessous "
                    "pointe sur localhost et ne fonctionnera que sur cette "
                    "machine. Cette clé doit être au premier niveau du fichier, "
                    "avant toute section entre crochets.",
                    icon="🚫",
                )
            base_url = configured_url or "http://localhost:8501"
            url = f"{base_url}/?session={session_id}&mode=student"
            st.image(_qr_png(url))
            st.caption("Les étudiants scannent ce code pour émarger.")
            st.link_button("Ouvrir la vue étudiant", url)

    with right:
        st.subheader("Émargements en direct")
        if session_id is None:
            _render_report_panel()
            _render_statistics(academic_year)
        else:
            _live_attendance(session_id, enrolled)
