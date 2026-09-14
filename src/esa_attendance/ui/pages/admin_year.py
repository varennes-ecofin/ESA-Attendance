"""Administration page: academic-year rollover, archiving and purge.

The yearly sequence is deliberately three explicit steps -- export, confirm,
purge -- rather than a single button: the purge is irreversible and the roster
files are the only remaining trace of who was enrolled.
"""

from __future__ import annotations

import streamlit as st

from ...roster.models import is_valid_academic_year
from ..login import require_role
from ..state import clear_roster_caches, get_repository, get_roster_service


def _render_year_switch() -> None:
    """Render the panel that changes the active academic year."""
    service = get_roster_service()
    current = service.current_academic_year()

    st.subheader("1. Année active")
    st.metric("Année en cours dans l'application", current)
    st.caption(
        "Toutes les sessions d'appel ouvertes à partir de maintenant seront "
        "rattachées à cette année, et les listes d'étudiants affichées seront "
        "celles importées pour elle."
    )

    target = st.text_input(
        "Basculer vers l'année", value=current, key="switch_year_value"
    ).strip()

    if not is_valid_academic_year(target):
        st.error("Format attendu : deux années consécutives, par exemple 2026-2027.")
        return

    if target == current:
        if service.has_explicit_academic_year():
            st.caption("C'est déjà l'année active.")
            return

        st.warning(
            "Cette année est **déduite de la date du jour**, elle n'est pas "
            "enregistrée. Tant qu'elle ne l'est pas, l'application basculera "
            "seule vers l'année suivante au 1er septembre prochain.",
            icon="⚠️",
        )
        if st.button("📌 Enregistrer cette année comme active", type="primary"):
            user = st.session_state.get("esa_user", {})
            service.set_current_academic_year(target, actor=str(user.get("username", "")))
            clear_roster_caches()
            st.success(f"Année active enregistrée : {target}.", icon="✅")
            st.rerun()
        return

    students = service.load_students(target)
    courses = service.load_courses(target)
    if not students or not courses:
        st.warning(
            f"L'année {target} n'a pas encore de liste "
            f"{'d\u2019étudiants' if not students else 'de cours'} complète "
            "(page « Référentiel »). La bascule reste possible, mais l'appel ne "
            "fonctionnera pas tant que les deux fichiers ne sont pas importés.",
            icon="⚠️",
        )
    else:
        st.info(
            f"{target} : {len(students)} étudiants et {len(courses)} cours prêts.",
            icon="✅",
        )

    confirmed = st.checkbox(
        f"Je confirme la bascule de {current} vers {target}.", key="switch_confirm"
    )
    if st.button("🔁 Basculer l'année active", type="primary", disabled=not confirmed):
        user = st.session_state.get("esa_user", {})
        service.set_current_academic_year(target, actor=str(user.get("username", "")))
        clear_roster_caches()
        st.success(f"Année active : {target}.", icon="✅")
        st.rerun()


def _render_archive_and_purge() -> None:
    """Render the export-then-purge panel for past academic years."""
    repository = get_repository("service")
    current = get_roster_service().current_academic_year()

    st.subheader("2. Archivage et purge des années passées")

    with st.spinner("Inventaire de la base…"):
        summary = repository.year_summary()

    if summary.empty:
        st.info("Aucune donnée de présence en base.")
        return

    display = summary.rename(
        columns={"academic_year": "Année", "sessions": "Sessions", "records": "Présences"}
    )
    st.dataframe(display, hide_index=True, width="stretch")

    purgeable = [
        year for year in summary["academic_year"].tolist() if year != current
    ]
    if not purgeable:
        st.caption("Seule l'année active est présente en base : rien à archiver.")
        return

    year = st.selectbox("Année à archiver puis purger", options=purgeable, key="purge_year")

    st.markdown("**Étape 1 — exporter l'archive**")
    with st.spinner(f"Extraction de {year}…"):
        archive = repository.export_year(year)

    if archive.empty:
        st.warning("Aucune ligne à exporter pour cette année.")
    else:
        downloaded = st.download_button(
            f"⬇️ Archive {year} ({len(archive)} lignes)",
            data=repository.to_archive_csv(archive),
            file_name=f"attendance_archive_{year}.csv",
            mime="text/csv",
            key="archive_download",
        )
        if downloaded:
            st.session_state[f"archived_{year}"] = True

    st.markdown("**Étape 2 — purger**")
    st.warning(
        f"La purge supprime définitivement les sessions et les présences de {year}. "
        "Les fichiers CSV du référentiel ne sont pas touchés.",
        icon="⚠️",
    )

    acknowledged = st.checkbox(
        "J'ai téléchargé et vérifié le fichier d'archive.", key="purge_ack"
    )
    typed = st.text_input(
        f"Pour confirmer, saisissez « {year} »", key="purge_typed"
    ).strip()

    ready = acknowledged and typed == year
    if st.button("🗑️ Purger définitivement", type="primary", disabled=not ready):
        try:
            result = repository.purge_year(year)
        except RuntimeError as exc:
            st.error(str(exc), icon="🚫")
            return
        st.success(
            f"{year} purgée : {result.get('deleted_sessions', 0)} sessions et "
            f"{result.get('deleted_records', 0)} présences supprimées.",
            icon="✅",
        )
        st.rerun()


def _render_maintenance() -> None:
    """Render small recurring maintenance operations."""
    st.subheader("3. Entretien")
    st.caption(
        "Une session laissée ouverte reste enregistrable par les étudiants et "
        "fausse les statistiques : elle n'est comptée nulle part tant qu'elle "
        "n'est pas fermée."
    )
    if st.button("🧹 Fermer les sessions ouvertes depuis plus de 12 h"):
        closed = get_repository("service").close_stale_sessions(older_than_hours=12)
        st.success(f"{closed} session(s) fermée(s).", icon="✅")


def render() -> None:
    """Render the academic-year administration page."""
    require_role("admin")
    st.title("📅 Année universitaire")
    _render_year_switch()
    st.markdown("---")
    _render_archive_and_purge()
    st.markdown("---")
    _render_maintenance()
