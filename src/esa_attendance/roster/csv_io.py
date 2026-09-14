"""Reading, validating and writing roster files.

Two input shapes are supported.

*The canonical file* is the one this application writes: one row per student,
columns ``academic_year, level, student_id, name``.

*The registrar file* is what the secretary receives: an Excel sheet with a
title line above the header, separate surname and first-name columns, unnamed
columns, and an administrative-registration status. The header row is located
by looking for known labels rather than assumed to be the first one.

Encoding and separator are detected, never assumed; empty cells are read as
empty strings, never as ``NaN``. E-mail columns are read and discarded: the
application never contacts students, so it does not store their addresses.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Mapping
from typing import Iterable, Sequence

import pandas as pd

from .models import LEVELS, Course, Student, ValidationReport, normalize_key

_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_SEPARATORS: str = ",;\t|"
_XLSX_MAGIC: bytes = b"PK\x03\x04"
_BLANKS: frozenset[str] = frozenset({"", "nan", "none", "null", "na", "n/a", "-"})
_HEADER_SCAN_ROWS = 12

STUDENT_COLUMNS: tuple[str, ...] = ("academic_year", "level", "student_id", "name")
COURSE_COLUMNS: tuple[str, ...] = ("code", "name", "level", "active")

STUDENT_ALIASES: dict[str, set[str]] = {
    "student_id": {"student_id", "id", "identifiant"},
    "name": {"name", "nom", "nom_prenom", "etudiant", "nom_complet"},
    "level": {"level", "niveau", "annee", "year", "promo", "promotion"},
    "academic_year": {"academic_year", "annee_universitaire", "annee_univ"},
}

REGISTRAR_ALIASES: dict[str, set[str]] = {
    "last_name": {
        "nom", "nom_patronymique", "nom_de_naissance", "nom_d_usage",
        "nom_de_famille", "nom_famille", "nom_usuel",
    },
    "first_name": {"prenom", "prenoms", "prenom_s"},
    "full_name": {"nom_prenom", "nom_complet", "etudiant", "name"},
    "level": {"level", "niveau", "promo", "promotion"},
    "status": {
        "inscription_administrative", "inscription", "statut", "situation",
        "etat_inscription",
    },
}

COURSE_ALIASES: dict[str, set[str]] = {
    "code": {"code", "course_code", "code_cours", "code_ue"},
    "name": {"name", "nom", "intitule", "libelle", "course_name"},
    "level": {"level", "niveau", "annee", "year"},
    "active": {"active", "actif", "ouvert", "enabled"},
}


# -----------------------------------------------------------------------------
# Decoding and header detection
# -----------------------------------------------------------------------------

def _decode(data: bytes) -> tuple[str, str]:
    """Decode raw bytes, trying the encodings Excel and pandas produce."""
    for encoding in _ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1 (dégradé)"


def _sniff_separator(text: str) -> str:
    """Detect the column separator of a CSV document."""
    sample = "\n".join(text.splitlines()[:5])
    try:
        return csv.Sniffer().sniff(sample, delimiters=_SEPARATORS).delimiter
    except csv.Error:
        header = text.splitlines()[0] if text.splitlines() else ""
        counts = {sep: header.count(sep) for sep in _SEPARATORS}
        best = max(counts, key=lambda sep: counts[sep])
        return best if counts[best] > 0 else ","


def normalize_label(value: object) -> str:
    """Normalize a column header: strip accents, lowercase, underscore spaces.

    ``"N° étudiant"`` becomes ``"n_etudiant"``, ``"Inscription administrative "``
    becomes ``"inscription_administrative"``.
    """
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_value = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.strip().lower()).strip("_")


def _detect_header_row(raw: pd.DataFrame, aliases: Mapping[str, set[str]]) -> int:
    """Return the index of the row holding the column headers.

    The registrar's files carry a title line above the header, so the first row
    cannot be assumed to be it.

    Args:
        raw: Frame read without a header.
        aliases: Alias mapping whose labels identify a header row.

    Returns:
        The row index, defaulting to 0 when nothing recognisable is found.
    """
    known: set[str] = set()
    for candidates in aliases.values():
        known |= candidates

    for index in range(min(_HEADER_SCAN_ROWS, len(raw))):
        labels = {normalize_label(value) for value in raw.iloc[index].tolist()}
        if labels & known:
            return index
    return 0


def read_table(
    data: bytes, aliases: Mapping[str, set[str]] | None = None
) -> tuple[pd.DataFrame, str]:
    """Read a CSV or XLSX file into a string-typed DataFrame.

    Args:
        data: Raw file content.
        aliases: Alias mapping used to locate the header row; when omitted, the
            first row is used as the header.

    Returns:
        A tuple ``(frame, description)`` where ``description`` documents how the
        file was interpreted, for display in the admin page.

    Raises:
        ValueError: If the file cannot be parsed at all.
    """
    if data[:4] == _XLSX_MAGIC:
        try:
            raw = pd.read_excel(io.BytesIO(data), header=None, dtype=str).fillna("")
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user
            raise ValueError(f"Fichier Excel illisible : {exc}") from exc
        description = "Excel (xlsx)"
    else:
        text, encoding = _decode(data)
        separator = _sniff_separator(text)
        try:
            raw = pd.read_csv(
                io.StringIO(text),
                sep=separator,
                header=None,
                dtype=str,
                keep_default_na=False,
                skip_blank_lines=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Fichier CSV illisible : {exc}") from exc
        printable = {"\t": "\\t"}.get(separator, separator)
        description = f"CSV (encodage {encoding}, séparateur « {printable} »)"

    raw = raw.map(lambda value: str(value).strip() if value is not None else "")

    header_index = _detect_header_row(raw, aliases) if aliases else 0
    headers = [
        normalize_label(value) or f"col_{position}"
        for position, value in enumerate(raw.iloc[header_index].tolist())
    ]

    frame = raw.iloc[header_index + 1 :].copy()
    frame.columns = headers
    frame = frame[~(frame == "").all(axis=1)]

    if header_index:
        description += f", en-tête ligne {header_index + 1}"
    return frame.reset_index(drop=True), description


def _resolve_columns(
    frame: pd.DataFrame, aliases: Mapping[str, set[str]]
) -> dict[str, str | None]:
    """Map canonical column names to the columns actually present."""
    return {
        canonical: next((c for c in frame.columns if c in candidates), None)
        for canonical, candidates in aliases.items()
    }


def _clean(value: object) -> str:
    """Collapse whitespace and map placeholder values to an empty string."""
    text = " ".join(str(value).split())
    return "" if text.lower() in _BLANKS else text


# -----------------------------------------------------------------------------
# Name composition
# -----------------------------------------------------------------------------

def _smart_title(value: str) -> str:
    """Title-case a first name, preserving hyphens and apostrophes.

    ``"JEAN-BAPTISTE"`` becomes ``"Jean-Baptiste"``.
    """
    parts = re.split(r"([ \-'])", value.lower())
    return "".join(part.capitalize() if part.isalpha() else part for part in parts)


def compose_name(last_name: str, first_name: str) -> str:
    """Build the display name from separate surname and first-name fields.

    The surname is upper-cased, matching the convention already used in the
    check-in list. A fully upper-cased first name is title-cased, since the
    registrar's files mix ``"Mèdéssé"`` and ``"AZIR"``; a first name that is
    already mixed-case is left untouched.

    Args:
        last_name: Surname as written in the file.
        first_name: First name as written in the file.

    Returns:
        The display name, e.g. ``"BEN YAGHLANE Aymen"``.
    """
    surname = " ".join(last_name.split()).upper()
    given = " ".join(first_name.split())
    if given.isupper():
        given = _smart_title(given)
    return f"{surname} {given}".strip()


# -----------------------------------------------------------------------------
# Canonical student file
# -----------------------------------------------------------------------------

def parse_students(
    frame: pd.DataFrame, academic_year: str
) -> tuple[list[Student], ValidationReport]:
    """Convert the canonical table into :class:`Student` objects.

    Args:
        frame: Table returned by :func:`read_table`.
        academic_year: Year assigned to rows that do not carry one.

    Returns:
        A tuple ``(students, report)``.
    """
    report = ValidationReport()
    columns = _resolve_columns(frame, STUDENT_ALIASES)

    for required in ("name", "level"):
        if columns[required] is None:
            report.error(f"Colonne obligatoire absente : « {required} »")
    if not report.ok:
        return [], report

    students: list[Student] = []
    seen_ids: dict[str, int] = {}

    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        name = _clean(row[columns["name"]])
        level = _clean(row[columns["level"]]).upper()
        if not name:
            continue
        if level not in LEVELS:
            report.error(f"Ligne {position} ({name}) : niveau « {level} » invalide")
            continue

        student_id = _clean(row[columns["student_id"]]) if columns["student_id"] else ""
        if student_id and student_id in seen_ids:
            report.error(
                f"Ligne {position} : identifiant « {student_id} » déjà utilisé "
                f"ligne {seen_ids[student_id]}"
            )
            continue
        if student_id:
            seen_ids[student_id] = position

        year = (
            _clean(row[columns["academic_year"]]) if columns["academic_year"] else ""
        ) or academic_year

        students.append(
            Student(student_id=student_id, name=name, level=level, academic_year=year)
        )

    if not students:
        report.error("Aucune ligne exploitable dans le fichier")
    return students, report


# -----------------------------------------------------------------------------
# Registrar file
# -----------------------------------------------------------------------------

def parse_registrar_table(
    frame: pd.DataFrame,
    level: str,
    academic_year: str,
    only_registered: bool = False,
) -> tuple[list[Student], ValidationReport, dict[str, int]]:
    """Convert a registrar export into :class:`Student` objects for one level.

    The level comes from the caller, not from the file: the registrar keeps one
    sheet per level and no column states it.

    Args:
        frame: Table returned by :func:`read_table` with
            :data:`REGISTRAR_ALIASES`.
        level: ``"M1"`` or ``"M2"``, chosen in the interface.
        academic_year: Year the import targets.
        only_registered: Keep only students whose administrative status starts
            with "inscrit".

    Returns:
        A tuple ``(students, report, status_counts)``. Identifiers are left
        empty: the roster service allocates them, reusing the identifier of a
        student already present.
    """
    report = ValidationReport()
    columns = _resolve_columns(frame, REGISTRAR_ALIASES)
    status_counts: dict[str, int] = {}

    has_split_name = columns["last_name"] is not None
    if not has_split_name and columns["full_name"] is None:
        report.error(
            "Aucune colonne de nom trouvée. Attendu « Nom » et « Prénom », "
            "ou une colonne « Nom Prénom »."
        )
        return [], report, status_counts

    students: list[Student] = []
    seen: dict[tuple[str, str], int] = {}
    skipped_status: list[str] = []
    skipped_level = 0

    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        # A file exported by this application carries its own level column; an
        # exported roster re-imported under the wrong radio button would
        # otherwise move every student to the selected level.
        if columns["level"] is not None:
            row_level = _clean(row[columns["level"]]).upper()
            if row_level and row_level != level:
                skipped_level += 1
                continue

        if has_split_name:
            last_name = _clean(row[columns["last_name"]])
            first_name = (
                _clean(row[columns["first_name"]]) if columns["first_name"] else ""
            )
            if not last_name:
                continue
            name = compose_name(last_name, first_name)
            if not first_name:
                report.warn(f"Ligne {position} : prénom manquant pour « {last_name} »")
        else:
            name = _clean(row[columns["full_name"]])
            if not name:
                continue

        raw_status = _clean(row[columns["status"]]) if columns["status"] else ""
        label = raw_status or "(non renseigné)"
        status_counts[label] = status_counts.get(label, 0) + 1

        registered = raw_status.lower().startswith("inscrit")
        if only_registered and not registered:
            skipped_status.append(f"{name} ({label})")
            continue
        if not registered and raw_status:
            report.warn(f"{name} : statut « {raw_status} »")

        key = (level, normalize_key(name))
        if key in seen:
            report.warn(
                f"Ligne {position} : « {name} » apparaît déjà ligne {seen[key]}"
            )
            continue
        seen[key] = position

        students.append(
            Student(student_id="", name=name, level=level, academic_year=academic_year)
        )

    if skipped_level:
        report.warn(
            f"{skipped_level} ligne(s) écartée(s) : le fichier indique un autre "
            f"niveau que {level}."
        )
    if skipped_status:
        report.warn(f"{len(skipped_status)} étudiant(s) écarté(s) : " + ", ".join(skipped_status))
    if not students:
        report.error("Aucun étudiant exploitable dans le fichier")

    return students, report, status_counts


def students_to_csv(students: Sequence[Student]) -> bytes:
    """Serialize students to the canonical UTF-8 CSV representation."""
    frame = pd.DataFrame(
        [
            {
                "academic_year": s.academic_year,
                "level": s.level,
                "student_id": s.student_id,
                "name": s.name,
            }
            for s in students
        ],
        columns=list(STUDENT_COLUMNS),
    )
    return frame.to_csv(index=False).encode("utf-8")


# -----------------------------------------------------------------------------
# Courses
# -----------------------------------------------------------------------------

def parse_courses(frame: pd.DataFrame) -> tuple[list[Course], ValidationReport]:
    """Convert a raw table into validated :class:`Course` objects."""
    report = ValidationReport()
    columns = _resolve_columns(frame, COURSE_ALIASES)

    for required in ("code", "name", "level"):
        if columns[required] is None:
            report.error(f"Colonne obligatoire absente : « {required} »")
    if not report.ok:
        return [], report

    courses: list[Course] = []
    seen: dict[str, int] = {}

    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        code = _clean(row[columns["code"]]).upper()
        name = _clean(row[columns["name"]])
        level = _clean(row[columns["level"]]).upper()

        if not code:
            continue
        if code in seen:
            report.error(f"Ligne {position} : code « {code} » déjà utilisé ligne {seen[code]}")
            continue
        if level not in LEVELS:
            report.error(f"Ligne {position} ({code}) : niveau « {level} » invalide")
            continue
        if not name:
            report.warn(f"Ligne {position} ({code}) : intitulé vide")

        raw_active = _clean(row[columns["active"]]).lower() if columns["active"] else ""
        active = raw_active not in {"0", "false", "non", "no", "n"} if raw_active else True

        seen[code] = position
        courses.append(Course(code=code, name=name or code, level=level, active=active))

    if not courses:
        report.error("Aucun cours exploitable dans le fichier")
    return courses, report


def courses_to_csv(courses: Iterable[Course]) -> bytes:
    """Serialize courses to the canonical UTF-8 CSV representation."""
    frame = pd.DataFrame(
        [
            {"code": c.code, "name": c.name, "level": c.level, "active": int(c.active)}
            for c in courses
        ],
        columns=list(COURSE_COLUMNS),
    )
    return frame.to_csv(index=False).encode("utf-8")
