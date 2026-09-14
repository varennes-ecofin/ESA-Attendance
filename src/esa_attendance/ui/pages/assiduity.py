"""Assiduity page: students with the lowest attendance rate over a period."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ...services.analytics import compute_assiduity
from ..login import require_role
from ..state import current_academic_year, get_repository, load_courses, load_students

DETAIL_TTL = 120


@st.cache_data(ttl=DETAIL_TTL, show_spinner=False)
def _attendance_detail(academic_year: str) -> pd.DataFrame:
    """Fetch the year's closed-session detail, cached for two minutes."""
    return get_repository("service").attendance_detail(academic_year)


def render() -> None:
    """Render the assiduity panel."""
    require_role()
    academic_year = current_academic_year()

    st.title("Assiduité")
    st.caption(f"Année {academic_year} — séances fermées uniquement.")

    courses = load_courses(academic_year)
    students = load_students(academic_year)
    if not courses or not students:
        st.warning(
            "Le référentiel de cette année est incomplet : importez les cours et "
            "les étudiants depuis la page « Référentiel ».",
            icon="📭",
        )
        st.stop()

    col_level, col_n, col_from, col_to = st.columns([1, 1, 2, 2])
    with col_level:
        level = st.selectbox("Niveau", options=["M1", "M2"])
    with col_n:
        top_n = st.number_input("Afficher", min_value=1, max_value=60, value=10)
    with col_from:
        date_from = st.date_input("Du", value=date(date.today().year, 1, 1))
    with col_to:
        date_to = st.date_input("Au", value=date.today())

    if date_from > date_to:
        st.warning("La date de début doit précéder la date de fin.")
        st.stop()

    level_courses = [c for c in courses if c.level == level]
    labels = {c.code: f"{c.name}" for c in level_courses}
    selected = st.multiselect(
        "Cours pris en compte (vide = tous les cours du niveau)",
        options=[c.code for c in level_courses],
        format_func=lambda code: labels[code],
    )

    with st.spinner("Calcul en cours…"):
        result = compute_assiduity(
            detail=_attendance_detail(academic_year),
            students=students,
            courses=courses,
            level=level,
            date_from=date_from,
            date_to=date_to,
            course_codes=selected or None,
            top_n=int(top_n),
        )

    if result.total_sessions == 0:
        st.info("Aucune séance fermée sur cette période pour cette sélection.")
        st.stop()

    st.metric("Séances retenues au dénominateur", result.total_sessions)

    if result.unmatched:
        st.warning(
            "Présences enregistrées pour des noms absents de la liste actuelle : "
            + ", ".join(result.unmatched),
            icon="⚠️",
        )

    display = result.frame.rename(
        columns={
            "student_name": "Étudiant",
            "sessions_attended": "Présences",
            "missed_sessions": "Absences",
            "attendance_rate": "Taux",
        }
    ).drop(columns=["student_id", "total_sessions"])
    display["Taux"] = display["Taux"].map(lambda value: f"{value:.0%}")

    st.dataframe(display, hide_index=True, width="stretch")

    st.download_button(
        "💾 Exporter en CSV",
        data=result.frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"assiduite_{level}_{date_from}_{date_to}.csv",
        mime="text/csv",
    )

    st.caption(
        "Le dénominateur compte toutes les séances fermées des cours retenus. "
        "Restreignez la sélection pour un cours optionnel que la promotion "
        "entière ne suit pas."
    )
