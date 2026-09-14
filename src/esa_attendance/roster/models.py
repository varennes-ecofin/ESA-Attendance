"""Domain models for the CSV-backed roster (students and courses)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Iterable, Literal

Level = Literal["M1", "M2"]
LEVELS: tuple[str, ...] = ("M1", "M2")

ACADEMIC_YEAR_RE = re.compile(r"^\d{4}-\d{4}$")


def normalize_key(name: str) -> str:
    """Return a comparison key for a student name.

    Accents are stripped, case is folded and inner whitespace collapsed, so that
    ``"NGOMA-BANKADILA  Roskane-Prestige"`` and ``"Ngoma-Bankadila Roskane-Prestige"``
    map to the same key. Used to match a student across two successive imports.

    Args:
        name: Raw name as written in the CSV file.

    Returns:
        A normalized, accent-free, uppercase key.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(ascii_name.upper().split())


def is_valid_academic_year(value: str) -> bool:
    """Return True if ``value`` matches the ``YYYY-YYYY`` convention."""
    if not ACADEMIC_YEAR_RE.match(value):
        return False
    start, end = (int(part) for part in value.split("-"))
    return end == start + 1


def academic_year_for(year: int, month: int) -> str:
    """Return the French academic year containing a given month.

    The year rolls over on September 1st, matching ``academic_year_of()`` in the
    SQL schema.

    Args:
        year: Calendar year.
        month: Calendar month, 1-12.

    Returns:
        The academic year, e.g. ``"2026-2027"``.
    """
    start = year if month >= 9 else year - 1
    return f"{start}-{start + 1}"


@dataclass(frozen=True)
class Student:
    """A student enrolled in a given level for a given academic year.

    No contact details are stored: the application never writes to students,
    so their addresses have no reason to be kept.

    Attributes:
        student_id: Stable identifier within the academic year, e.g. ``m1_007``.
            May be empty right after parsing; the roster service allocates it.
        name: Display name as it appears in the check-in list.
        level: ``"M1"`` or ``"M2"``.
        academic_year: Owning academic year, e.g. ``"2026-2027"``.
    """

    student_id: str
    name: str
    level: str
    academic_year: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """Return the ``(level, normalized name)`` identity key."""
        return (self.level, normalize_key(self.name))

    def with_id(self, student_id: str) -> "Student":
        """Return a copy of this student carrying ``student_id``."""
        return replace(self, student_id=student_id)


@dataclass(frozen=True)
class Course:
    """A course offered in a given level.

    Attributes:
        code: Course code used as ``attendance_sessions.course_code``.
        name: Human-readable course name.
        level: ``"M1"`` or ``"M2"``.
        active: Whether the course is proposed in the session dropdown.
    """

    code: str
    name: str
    level: str
    active: bool = True

    @property
    def label(self) -> str:
        """Return the string displayed in the course selector."""
        return f"{self.name} ({self.level})"


COURSE_CODE_RE = re.compile(r"^ESA([12])([A-Z]{2})(\d{2})$")

COURSE_FAMILIES: dict[str, str] = {
    "AN": "Analyse de données",
    "AS": "Assurance et actuariat",
    "BD": "Big data et apprentissage",
    "CO": "Communication",
    "DM": "Data mining",
    "EC": "Économétrie",
    "EN": "Anglais",
    "FI": "Finance",
    "PJ": "Projet et entreprise",
    "PR": "Programmation",
    "RE": "Réglementation",
    "SE": "Séminaire",
    "ST": "Statistique",
}


def course_family(code: str) -> str:
    """Return the two-letter discipline of a course code.

    Args:
        code: Course code, e.g. ``"ESA1PR03"``.

    Returns:
        The discipline, e.g. ``"PR"``, or an empty string when the code does not
        follow the convention.
    """
    match = COURSE_CODE_RE.match(code.strip().upper())
    return match.group(2) if match else ""


def allocate_course_code(existing: Iterable[str], level: str, family: str) -> str:
    """Build the next free course code for a discipline and level.

    Codes are never reused, even after a course is deactivated: the code of a
    retired course still appears in past attendance sessions, so handing it to
    a new course would silently merge two different courses in the statistics.

    Args:
        existing: Every code already in use, active or not.
        level: ``"M1"`` or ``"M2"``.
        family: Two-letter discipline, e.g. ``"PR"``.

    Returns:
        A code of the form ``ESA1PR07``.

    Raises:
        ValueError: If the level or family is malformed, or the 99 slots of the
            family are exhausted.
    """
    if level not in LEVELS:
        raise ValueError(f"Niveau invalide : {level!r}")
    family = family.strip().upper()
    if len(family) != 2 or not family.isalpha():
        raise ValueError(f"Domaine invalide : {family!r}")

    digit = "1" if level == "M1" else "2"
    used = {str(code).strip().upper() for code in existing}
    for number in range(1, 100):
        candidate = f"ESA{digit}{family}{number:02d}"
        if candidate not in used:
            return candidate
    raise ValueError(f"Aucun code disponible pour {digit}{family}")


@dataclass
class ValidationReport:
    """Outcome of parsing a roster file.

    Errors block the import; warnings are shown but do not.
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the file can be imported."""
        return not self.errors

    def error(self, message: str) -> None:
        """Record a blocking problem."""
        self.errors.append(message)

    def warn(self, message: str) -> None:
        """Record a non-blocking problem."""
        self.warnings.append(message)

    def extend(self, other: "ValidationReport") -> None:
        """Merge another report into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


@dataclass(frozen=True)
class RosterDiff:
    """Difference between the roster in place and the one being imported.

    Attributes:
        added: Students present only in the new roster.
        removed: Students present only in the previous roster.
        kept: Pairs ``(previous, new)`` matched on ``(level, normalized name)``.
    """

    added: tuple[Student, ...]
    removed: tuple[Student, ...]
    kept: tuple[tuple[Student, Student], ...]

    @classmethod
    def between(
        cls, previous: Iterable[Student], new: Iterable[Student]
    ) -> "RosterDiff":
        """Compute the diff between two rosters.

        Args:
            previous: Roster currently stored.
            new: Roster about to replace it.

        Returns:
            The corresponding :class:`RosterDiff`.
        """
        old_by_key = {s.key: s for s in previous}
        new_by_key = {s.key: s for s in new}

        added = tuple(s for k, s in new_by_key.items() if k not in old_by_key)
        removed = tuple(s for k, s in old_by_key.items() if k not in new_by_key)
        kept = tuple(
            (old_by_key[k], new_by_key[k]) for k in new_by_key if k in old_by_key
        )
        return cls(added=added, removed=removed, kept=kept)

    def summary(self) -> str:
        """Return a one-line human summary of the diff."""
        return (
            f"{len(self.added)} arrivée(s), "
            f"{len(self.removed)} sortie(s), "
            f"{len(self.kept)} inchangé(s)"
        )
