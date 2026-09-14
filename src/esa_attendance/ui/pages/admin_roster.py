"""Administration page: build and maintain the roster files.

Three workflows, deliberately separated because they happen at different
moments of the year.

*Import* takes the registrar's spreadsheet for one level. M2 is known in July,
M1 keeps moving until October, so an import replaces one level and leaves the
other alone.

*Manual editing* handles the exceptions an import cannot: a late foreign
enrolment, a student dropping out in November.

*Courses* changes about once a year and keeps its own tab.

Nothing is written before the file has been parsed, validated and shown as a
diff, and every write keeps a timestamped backup.
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st

from ...roster.models import (
    COURSE_FAMILIES,
    LEVELS,
    Course,
    Student,
    ValidationReport,
    allocate_course_code,
    course_family,
    is_valid_academic_year,
)
from ...roster.service import CoursePreview, RosterService, StudentPreview
from ..login import require_role
from ..state import clear_roster_caches, get_repository, get_roster_service

NEW_YEAR_OPTION = "➕ Nouvelle année…"


# ---------------------------------------------------------------------------
# Shared widgets
# ---------------------------------------------------------------------------

def select_target_year(service: RosterService, key: str) -> str | None:
    """Render the academic-year selector.

    Args:
        service: Roster service used to list the known years.
        key: Prefix used for the widget keys.

    Returns:
        The selected year, or ``None`` when the free-text entry is invalid.
    """
    known = service.known_academic_years()
    choice = st.selectbox(
        "Année universitaire", options=[*known, NEW_YEAR_OPTION], key=f"{key}_choice"
    )
    if choice != NEW_YEAR_OPTION:
        return choice

    raw = st.text_input(
        "Nouvelle année (format AAAA-AAAA)", placeholder="2026-2027", key=f"{key}_new"
    ).strip()
    if not raw:
        return None
    if not is_valid_academic_year(raw):
        st.error("Format attendu : deux années consécutives, par exemple 2026-2027.")
        return None
    return raw


def _render_report(report: ValidationReport) -> None:
    """Display validation errors and warnings."""
    for message in report.errors:
        st.error(message, icon="🚫")
    if report.warnings:
        with st.expander(f"⚠️ {len(report.warnings)} point(s) à vérifier"):
            for message in report.warnings:
                st.write(f"- {message}")


def _names_frame(students: tuple[Student, ...] | list[Student]) -> pd.DataFrame:
    """Return a display-ready frame of students."""
    return pd.DataFrame(
        [{"Identifiant": s.student_id, "Nom": s.name} for s in students],
        columns=["Identifiant", "Nom"],
    )


# ---------------------------------------------------------------------------
# Import from the registrar's file
# ---------------------------------------------------------------------------

def _render_preview(preview: StudentPreview) -> None:
    """Show the counts, the statuses found and the diff."""
    left, middle, right = st.columns(3)
    left.metric("Étudiants retenus", len(preview.students))
    middle.metric("Arrivées", len(preview.diff.added))
    right.metric("Sorties", len(preview.diff.removed))

    if preview.status_counts:
        summary = " · ".join(
            f"{label} : {count}" for label, count in sorted(preview.status_counts.items())
        )
        st.caption(f"Statuts d'inscription dans le fichier — {summary}")

    if preview.diff.added:
        with st.expander(f"➕ {len(preview.diff.added)} arrivée(s)"):
            st.dataframe(_names_frame(preview.diff.added), hide_index=True, width="stretch")
    if preview.diff.removed:
        with st.expander(f"➖ {len(preview.diff.removed)} sortie(s)"):
            st.dataframe(_names_frame(preview.diff.removed), hide_index=True, width="stretch")
    with st.expander(f"📄 Liste complète ({len(preview.students)})"):
        st.dataframe(_names_frame(preview.students), hide_index=True, width="stretch")


def _render_import(service: RosterService, year: str, level: str) -> None:
    """Render the registrar-file import workflow for one level."""
    st.markdown(
        "Déposez le fichier d'inscription de la scolarité, tel quel. Les colonnes "
        "**Nom** et **Prénom** suffisent ; le titre au-dessus de l'en-tête, le "
        "numéro d'ordre et les colonnes d'e-mail sont ignorés. Les adresses ne "
        "sont jamais enregistrées."
    )

    only_registered = st.checkbox(
        "N'importer que les étudiants dont l'inscription administrative est confirmée",
        key=f"only_registered_{level}",
        help=(
            "Décoché, tous les étudiants sont importés et ceux dont le statut "
            "n'est pas « Inscrit » sont simplement signalés."
        ),
    )

    sequence = st.session_state.setdefault(f"upload_seq_{level}", 0)
    uploaded = st.file_uploader(
        f"Fichier des {level} (Excel ou CSV)",
        type=["xlsx", "xls", "csv"],
        key=f"upload_{level}_{sequence}",
    )
    if uploaded is None:
        return

    try:
        preview = service.preview_registrar_file(
            uploaded.getvalue(), year, level, only_registered
        )
    except ValueError as exc:
        st.error(str(exc), icon="🚫")
        return

    st.caption(f"Fichier interprété comme : {preview.source_description}")
    _render_report(preview.report)
    if not preview.report.ok:
        return

    _render_preview(preview)

    st.markdown("---")
    # The key carries the sequence number: resetting the checkbox by assigning
    # to st.session_state is forbidden once the widget has been instantiated,
    # so a fresh widget is created instead.
    confirmed = st.checkbox(
        f"Je confirme le remplacement de la liste {level} de {year}.",
        key=f"confirm_{level}_{sequence}",
    )
    if st.button(
        f"💾 Remplacer la liste {level}",
        type="primary",
        disabled=not confirmed,
        key=f"commit_{level}",
    ):
        backup = service.commit_students_for_level(year, level, preview.students)
        clear_roster_caches()
        st.session_state[f"upload_seq_{level}"] = sequence + 1
        message = f"Liste {level} remplacée : {len(preview.students)} étudiants."
        if backup:
            message += f" Sauvegarde : `{backup}`."
        st.success(message, icon="✅")
        st.rerun()


# ---------------------------------------------------------------------------
# Manual editing
# ---------------------------------------------------------------------------

def _render_editor(service: RosterService, year: str, level: str) -> None:
    """Render the editable table for one level."""
    current = sorted(
        (s for s in service.load_students(year) if s.level == level),
        key=lambda s: s.name,
    )

    st.markdown(
        "Modifiez un nom, ajoutez une ligne avec le **+** en bas du tableau, ou "
        "supprimez une ligne en la sélectionnant puis avec la touche Suppr. "
        "Les identifiants sont attribués à l'enregistrement et ne s'éditent pas."
    )

    edited = st.data_editor(
        pd.DataFrame(
            [{"Identifiant": s.student_id, "Nom": s.name} for s in current]
            or [{"Identifiant": "", "Nom": ""}]
        ),
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Identifiant": st.column_config.TextColumn("Identifiant", disabled=True),
            "Nom": st.column_config.TextColumn(
                "Nom", required=True, help="Format : NOM Prénom"
            ),
        },
        key=f"editor_{level}_{year}",
    )

    names = [str(value).strip() for value in edited["Nom"].tolist() if str(value).strip()]
    previous_names = [s.name for s in current]

    added = sorted(set(names) - set(previous_names))
    removed = sorted(set(previous_names) - set(names))

    if not added and not removed:
        st.caption(f"{len(names)} étudiant(s) — aucune modification en attente.")
        return

    if added:
        st.info("À ajouter : " + ", ".join(added), icon="➕")
    if removed:
        st.warning("À retirer : " + ", ".join(removed), icon="➖")

    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        st.error("Nom en double : " + ", ".join(sorted(duplicates)), icon="🚫")
        return

    if st.button(
        f"💾 Enregistrer la liste {level}", type="primary", key=f"save_editor_{level}"
    ):
        backup, resolved = service.replace_level_from_editor(year, level, names)
        clear_roster_caches()
        message = f"Liste {level} enregistrée : {len(resolved)} étudiants."
        if backup:
            message += f" Sauvegarde : `{backup}`."
        st.success(message, icon="✅")
        st.rerun()


# ---------------------------------------------------------------------------
# Students tab
# ---------------------------------------------------------------------------

def _render_students_tab(service: RosterService, year: str) -> None:
    """Render the per-level student workflows."""
    students = service.load_students(year)
    counts = {level: sum(1 for s in students if s.level == level) for level in LEVELS}

    header, download = st.columns([3, 1])
    with header:
        st.caption(
            f"Listes en place pour {year} — "
            + " · ".join(f"{level} : {counts[level]}" for level in LEVELS)
        )
    with download:
        if students:
            st.download_button(
                "⬇️ Exporter",
                data=service.export_students(year),
                file_name=f"etudiants_{year}.csv",
                mime="text/csv",
                key="download_students",
            )

    level = st.radio(
        "Niveau", options=list(LEVELS), horizontal=True, key="roster_level"
    )

    import_tab, edit_tab = st.tabs(["📥 Importer une liste", "✏️ Éditer la liste"])
    with import_tab:
        _render_import(service, year, level)
    with edit_tab:
        _render_editor(service, year, level)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

FAMILY_LABELS: dict[str, str] = {
    f"{code} — {label}": code for code, label in COURSE_FAMILIES.items()
}


def _courses_frame(courses: Sequence[Course]) -> pd.DataFrame:
    """Return a display-ready frame of courses."""
    return pd.DataFrame(
        [
            {
                "Code": c.code,
                "Intitulé": c.name,
                "Niveau": c.level,
                "Actif": "oui" if c.active else "non",
            }
            for c in courses
        ]
    )


def _session_counts(year: str) -> dict[str, int]:
    """Return the number of closed sessions per course code for a year.

    Used to protect codes that history depends on. Failures are swallowed: this
    is an advisory guard, not a reason to block the page.
    """
    try:
        stats = get_repository("service").course_stats(year)
    except Exception:  # noqa: BLE001 -- advisory only
        return {}
    if stats.empty:
        return {}
    return {
        str(row["course_code"]): int(row["num_sessions"])
        for row in stats.to_dict("records")
    }


def _render_courses_import(service: RosterService, year: str) -> None:
    """Render the full-catalogue import workflow."""
    st.markdown(
        "Remplace **tout** le catalogue de l'année. À réserver à la mise en place "
        "d'une nouvelle année : pour ajouter ou retirer un cours, utilisez "
        "l'onglet d'édition, qui préserve les codes existants."
    )
    st.markdown(
        "**Colonnes attendues** : `code`, `name`, `level` ; `active` facultative "
        "(0 pour retirer un cours du menu sans l'effacer)."
    )

    sequence = st.session_state.setdefault("courses_upload_seq", 0)
    uploaded = st.file_uploader(
        "Maquette (CSV ou Excel)",
        type=["csv", "xlsx", "xls"],
        key=f"courses_upload_{sequence}",
    )
    if uploaded is None:
        return

    try:
        preview: CoursePreview = service.preview_courses(uploaded.getvalue())
    except ValueError as exc:
        st.error(str(exc), icon="🚫")
        return

    st.caption(f"Fichier interprété comme : {preview.source_description}")
    _render_report(preview.report)
    if not preview.report.ok:
        return

    current_codes = {c.code for c in service.load_courses(year)}
    new_codes = {c.code for c in preview.courses}
    dropped = sorted(current_codes - new_codes)
    counts = _session_counts(year)
    at_risk = [code for code in dropped if counts.get(code)]

    st.metric("Cours dans le fichier", len(preview.courses))
    if at_risk:
        st.error(
            "Ces codes disparaîtraient alors que des séances y font référence : "
            + ", ".join(f"{code} ({counts[code]} séances)" for code in at_risk)
            + ". Leurs statistiques passeraient en « hors catalogue ».",
            icon="🚫",
        )
    elif dropped:
        st.warning("Codes retirés : " + ", ".join(dropped), icon="➖")

    with st.expander("📄 Aperçu"):
        st.dataframe(_courses_frame(preview.courses), hide_index=True, width="stretch")

    confirmed = st.checkbox(
        f"Je confirme le remplacement du catalogue de {year}.",
        key=f"courses_confirm_{sequence}",
    )
    if st.button(
        "💾 Remplacer le catalogue",
        type="primary",
        disabled=not confirmed,
        key="courses_commit",
    ):
        backup = service.commit_courses(year, preview.courses)
        clear_roster_caches()
        st.session_state["courses_upload_seq"] = sequence + 1
        message = f"Catalogue remplacé : {len(preview.courses)} cours."
        if backup:
            message += f" Sauvegarde : `{backup}`."
        st.success(message, icon="✅")
        st.rerun()


def _build_courses(edited: pd.DataFrame, existing: Sequence[Course]) -> tuple[list[Course], list[str]]:
    """Turn the edited table back into courses, allocating codes for new rows.

    Args:
        edited: Frame returned by the data editor.
        existing: Catalogue currently stored, whose codes are never reused.

    Returns:
        The resulting courses and the list of blocking problems.
    """
    reserved = {c.code for c in existing}
    courses: list[Course] = []
    problems: list[str] = []

    for position, row in enumerate(edited.to_dict("records"), start=1):
        name = " ".join(str(row.get("Intitulé") or "").split())
        level = str(row.get("Niveau") or "").strip().upper()
        code = str(row.get("Code") or "").strip().upper()
        family = FAMILY_LABELS.get(str(row.get("Domaine") or ""), "")
        active = bool(row.get("Actif", True))

        if not name and not code:
            continue
        if not name:
            problems.append(f"Ligne {position} : intitulé manquant")
            continue
        if level not in LEVELS:
            problems.append(f"Ligne {position} ({name}) : niveau manquant")
            continue

        if not code:
            if not family:
                problems.append(f"Ligne {position} ({name}) : domaine manquant")
                continue
            try:
                code = allocate_course_code(reserved, level, family)
            except ValueError as exc:
                problems.append(f"Ligne {position} ({name}) : {exc}")
                continue
            reserved.add(code)

        courses.append(Course(code=code, name=name, level=level, active=active))

    seen: set[str] = set()
    for course in courses:
        if course.code in seen:
            problems.append(f"Code en double : {course.code}")
        seen.add(course.code)

    return courses, problems


def _render_courses_editor(service: RosterService, year: str) -> None:
    """Render the editable catalogue for marginal year-to-year adjustments."""
    current = sorted(service.load_courses(year), key=lambda c: (c.level, c.code))
    if not current:
        st.info("Importez d'abord une maquette : l'éditeur part du catalogue en place.")
        return

    counts = _session_counts(year)
    st.markdown(
        "Ajoutez un cours avec le **+** en bas du tableau : le code est attribué "
        "à l'enregistrement à partir du niveau et du domaine. Pour retirer un "
        "cours de la maquette, **décochez « Actif »** plutôt que de supprimer la "
        "ligne : il quitte le menu des enseignants tout en restant lisible dans "
        "l'historique."
    )

    reverse_labels = {code: label for label, code in FAMILY_LABELS.items()}
    frame = pd.DataFrame(
        [
            {
                "Code": c.code,
                "Niveau": c.level,
                "Domaine": reverse_labels.get(course_family(c.code), ""),
                "Intitulé": c.name,
                "Actif": c.active,
                "Séances": counts.get(c.code, 0),
            }
            for c in current
        ]
    )

    edited = st.data_editor(
        frame,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Code": st.column_config.TextColumn(
                "Code", disabled=True, help="Attribué automatiquement, jamais modifié"
            ),
            "Niveau": st.column_config.SelectboxColumn(
                "Niveau", options=list(LEVELS), required=True
            ),
            "Domaine": st.column_config.SelectboxColumn(
                "Domaine", options=list(FAMILY_LABELS), required=False
            ),
            "Intitulé": st.column_config.TextColumn("Intitulé", required=True),
            "Actif": st.column_config.CheckboxColumn("Actif", default=True),
            "Séances": st.column_config.NumberColumn(
                "Séances", disabled=True, help="Séances fermées enregistrées pour ce code"
            ),
        },
        key=f"courses_editor_{year}",
    )

    courses, problems = _build_courses(edited, current)

    kept = {c.code for c in courses}
    removed = [c.code for c in current if c.code not in kept]
    destructive = [code for code in removed if counts.get(code)]
    if destructive:
        problems.append(
            "Suppression impossible, des séances y font référence : "
            + ", ".join(f"{code} ({counts[code]} séances)" for code in destructive)
            + ". Décochez « Actif » à la place."
        )

    for problem in problems:
        st.error(problem, icon="🚫")
    if problems:
        return

    added = [c.code for c in courses if c.code not in {x.code for x in current}]
    changed = [
        c.code
        for c in courses
        for old in current
        if old.code == c.code and (old.name != c.name or old.active != c.active or old.level != c.level)
    ]

    if not added and not changed and not removed:
        st.caption(f"{len(courses)} cours — aucune modification en attente.")
        return

    if added:
        st.info("Nouveaux codes attribués à l'enregistrement : " + ", ".join(added), icon="➕")
    if changed:
        st.info("Modifiés : " + ", ".join(changed), icon="✏️")
    if removed:
        st.warning("Supprimés : " + ", ".join(removed), icon="➖")

    if st.button("💾 Enregistrer le catalogue", type="primary", key="courses_editor_save"):
        backup = service.commit_courses(year, courses)
        clear_roster_caches()
        message = f"Catalogue enregistré : {len(courses)} cours."
        if backup:
            message += f" Sauvegarde : `{backup}`."
        st.success(message, icon="✅")
        st.rerun()


def _render_courses_tab(service: RosterService, year: str) -> None:
    """Render the catalogue workflows."""
    current = service.load_courses(year)
    if current:
        active = sum(1 for c in current if c.active)
        head, download = st.columns([3, 1])
        with head:
            st.caption(
                f"Catalogue {year} — {len(current)} cours dont {active} actifs."
            )
        with download:
            st.download_button(
                "⬇️ Exporter",
                data=service.export_courses(year),
                file_name=f"cours_{year}.csv",
                mime="text/csv",
                key="download_courses",
            )
    else:
        st.warning(
            f"Aucun catalogue pour {year}. Exportez celui de l'année précédente "
            "et réimportez-le ici : la maquette bouge peu d'une année sur l'autre.",
            icon="📭",
        )

    edit_tab, import_tab = st.tabs(["✏️ Éditer le catalogue", "📥 Importer une maquette"])
    with edit_tab:
        _render_courses_editor(service, year)
    with import_tab:
        _render_courses_import(service, year)


# ---------------------------------------------------------------------------
# Backups tab
# ---------------------------------------------------------------------------

def _render_backups(service: RosterService, year: str) -> None:
    """Render the restore panel for the backups of a year."""
    backups = service.list_backups(year)
    if not backups:
        st.caption("Aucune sauvegarde pour cette année.")
        return

    selected = st.selectbox("Sauvegarde à restaurer", options=backups, key="backup_choice")
    confirmed = st.checkbox(
        "Je confirme la restauration (la liste actuelle sera elle-même sauvegardée).",
        key="backup_confirm",
    )
    if st.button("↩️ Restaurer", disabled=not confirmed, key="backup_restore"):
        try:
            service.restore_backup(selected, year)
        except (FileNotFoundError, ValueError) as exc:
            st.error(f"Restauration impossible : {exc}", icon="🚫")
            return
        clear_roster_caches()
        st.success(f"Sauvegarde `{selected}` restaurée.", icon="✅")
        st.rerun()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the roster administration page."""
    require_role("admin")
    service = get_roster_service()

    st.title("🗂️ Référentiel")
    st.caption(
        f"Année active de l'application : **{service.current_academic_year()}**. "
        "Importer une liste ne change pas l'année active : cela se fait dans "
        "« Année universitaire »."
    )

    year = select_target_year(service, key="roster_year")
    if year is None:
        st.stop()

    students_tab, courses_tab, backups_tab = st.tabs(
        ["👥 Étudiants", "📚 Cours", "🗄️ Sauvegardes"]
    )
    with students_tab:
        _render_students_tab(service, year)
    with courses_tab:
        _render_courses_tab(service, year)
    with backups_tab:
        _render_backups(service, year)
