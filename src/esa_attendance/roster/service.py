"""Roster orchestration: load, preview, replace and version the CSV files.

Layout inside the store::

    manifest.json                       {"current_academic_year": "2026-2027"}
    2026-2027/students.csv
    2026-2027/courses.csv
    2026-2027/backups/students-20260913-101500.csv
    2026-2027/backups/courses-20260913-101500.csv

Every replacement writes a timestamped backup first, so a bad import made by a
non-technical user is always one click away from being undone.

This module contains no Streamlit call: it is pure logic, testable offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from ..config import Settings, get_settings
from .csv_io import (
    COURSE_ALIASES,
    REGISTRAR_ALIASES,
    STUDENT_ALIASES,
    courses_to_csv,
    parse_courses,
    parse_registrar_table,
    parse_students,
    read_table,
    students_to_csv,
)
from .models import (
    LEVELS,
    Course,
    RosterDiff,
    Student,
    ValidationReport,
    academic_year_for,
    is_valid_academic_year,
)
from .store import LocalRosterStore, RosterStore, SupabaseRosterStore

MANIFEST_PATH = "manifest.json"
STUDENTS_FILE = "students.csv"
COURSES_FILE = "courses.csv"


def default_academic_year() -> str:
    """Return the academic year containing today's date."""
    today = datetime.now()
    return academic_year_for(today.year, today.month)


@dataclass(frozen=True)
class StudentPreview:
    """Result of parsing a registrar file for one level, before committing.

    Attributes:
        students: Parsed students, identifiers already allocated.
        report: Errors and warnings raised while parsing.
        diff: Comparison with the students of the same level currently stored.
        source_description: How the file was interpreted.
        level: Level the import targets.
        status_counts: Administrative statuses found, with their counts.
    """

    students: tuple[Student, ...]
    report: ValidationReport
    diff: RosterDiff
    source_description: str
    level: str = ""
    status_counts: dict[str, int] = field(default_factory=dict)

    def counts_by_level(self) -> dict[str, int]:
        """Return the number of students per level."""
        return {
            level: sum(1 for s in self.students if s.level == level) for level in LEVELS
        }


@dataclass(frozen=True)
class CoursePreview:
    """Result of parsing an uploaded course file, before it is committed."""

    courses: tuple[Course, ...]
    report: ValidationReport
    source_description: str


class RosterService:
    """Read and write the roster files held in a :class:`RosterStore`."""

    def __init__(self, store: RosterStore) -> None:
        """Initialize the service.

        Args:
            store: Backend holding the roster tree.
        """
        self._store = store

    # ------------------------------------------------------------------
    # Manifest / current academic year
    # ------------------------------------------------------------------

    def _read_manifest(self) -> dict[str, str]:
        """Return the manifest content, or an empty mapping."""
        raw = self._store.read(MANIFEST_PATH)
        if raw is None:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def current_academic_year(self) -> str:
        """Return the active academic year.

        Falls back to the year derived from today's date when no manifest has
        been written yet.
        """
        value = self._read_manifest().get("current_academic_year", "")
        return value if is_valid_academic_year(value) else default_academic_year()

    def has_explicit_academic_year(self) -> bool:
        """Return True when the active year is recorded in the manifest.

        When it is not, :meth:`current_academic_year` falls back to the year
        derived from today's date, which silently rolls over on September 1st.
        """
        return is_valid_academic_year(
            self._read_manifest().get("current_academic_year", "")
        )

    def set_current_academic_year(self, year: str, actor: str = "") -> None:
        """Switch the active academic year.

        Args:
            year: Target year, formatted ``YYYY-YYYY``.
            actor: Username recorded in the manifest for traceability.

        Raises:
            ValueError: If ``year`` is malformed.
        """
        if not is_valid_academic_year(year):
            raise ValueError(f"Invalid academic year: {year!r} (expected e.g. 2026-2027)")

        manifest = self._read_manifest()
        manifest.update(
            {
                "current_academic_year": year,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "updated_by": actor,
            }
        )
        self._store.write(
            MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        )

    def known_academic_years(self) -> list[str]:
        """Return every year for which at least one roster file exists."""
        years = {
            path.split("/", 1)[0]
            for path in self._store.list("")
            if "/" in path or is_valid_academic_year(path)
        }
        years |= {
            entry.rstrip("/")
            for entry in self._store.list("")
            if is_valid_academic_year(entry.rstrip("/"))
        }
        years = {y for y in years if is_valid_academic_year(y)}
        years.add(self.current_academic_year())
        return sorted(years, reverse=True)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_students(self, year: str | None = None) -> list[Student]:
        """Return the students enrolled for ``year``.

        Args:
            year: Academic year; defaults to the active one.

        Returns:
            The students, or an empty list when no file has been imported yet.
        """
        year = year or self.current_academic_year()
        raw = self._store.read(f"{year}/{STUDENTS_FILE}")
        if raw is None:
            return []
        frame, _ = read_table(raw, STUDENT_ALIASES)
        students, _ = parse_students(frame, year)
        return students

    def load_courses(self, year: str | None = None) -> list[Course]:
        """Return the courses offered for ``year`` (empty list if not imported)."""
        year = year or self.current_academic_year()
        raw = self._store.read(f"{year}/{COURSES_FILE}")
        if raw is None:
            return []
        frame, _ = read_table(raw, COURSE_ALIASES)
        courses, _ = parse_courses(frame)
        return courses

    def students_by_level(self, level: str, year: str | None = None) -> list[Student]:
        """Return the students of a given level, sorted by name."""
        return sorted(
            (s for s in self.load_students(year) if s.level == level),
            key=lambda s: s.name,
        )

    # ------------------------------------------------------------------
    # Identifier reconciliation
    # ------------------------------------------------------------------

    @staticmethod
    def _allocate_ids(
        students: Sequence[Student], previous: Sequence[Student]
    ) -> list[Student]:
        """Give every student a stable identifier.

        A student already present in the previous roster keeps their identifier,
        so that a mid-year re-import (one late enrolment, one correction) does
        not renumber everyone and orphan the attendance already recorded.

        Args:
            students: Freshly parsed students, some without an identifier.
            previous: Roster currently stored for the same year.

        Returns:
            The same students, in the same order, all carrying an identifier.
        """
        previous_by_key = {s.key: s.student_id for s in previous if s.student_id}
        taken = {s.student_id for s in students if s.student_id}
        counters = {level: 0 for level in LEVELS}

        resolved: list[Student] = []
        for student in students:
            if student.student_id:
                resolved.append(student)
                continue

            inherited = previous_by_key.get(student.key, "")
            if inherited and inherited not in taken:
                taken.add(inherited)
                resolved.append(student.with_id(inherited))
                continue

            prefix = student.level.lower()
            while True:
                counters[student.level] = counters.get(student.level, 0) + 1
                candidate = f"{prefix}_{counters[student.level]:03d}"
                if candidate not in taken:
                    break
            taken.add(candidate)
            resolved.append(student.with_id(candidate))

        return resolved

    # ------------------------------------------------------------------
    # Import workflow: preview then commit
    # ------------------------------------------------------------------

    def preview_registrar_file(
        self,
        data: bytes,
        year: str,
        level: str,
        only_registered: bool = False,
    ) -> StudentPreview:
        """Parse a registrar file for one level, without writing anything.

        Args:
            data: Raw content of the uploaded file.
            year: Academic year the import targets.
            level: ``"M1"`` or ``"M2"``; the file itself does not state it.
            only_registered: Drop students whose administrative status is not
                "inscrit".

        Returns:
            The parsed students, the validation report, the registration
            statuses found, and the diff against the students of the same level
            currently stored.
        """
        frame, description = read_table(data, REGISTRAR_ALIASES)
        students, report, statuses = parse_registrar_table(
            frame, level, year, only_registered
        )
        previous = [s for s in self.load_students(year) if s.level == level]
        students = self._allocate_ids(students, previous)
        return StudentPreview(
            students=tuple(students),
            report=report,
            diff=RosterDiff.between(previous, students),
            source_description=description,
            level=level,
            status_counts=statuses,
        )

    def preview_courses(self, data: bytes) -> CoursePreview:
        """Parse an uploaded course file without writing anything."""
        frame, description = read_table(data, COURSE_ALIASES)
        courses, report = parse_courses(frame)
        return CoursePreview(
            courses=tuple(courses), report=report, source_description=description
        )

    def _backup(self, year: str, filename: str) -> str | None:
        """Copy the current file to the backup folder.

        Returns:
            The backup path, or ``None`` when there was nothing to back up.
        """
        current = self._store.read(f"{year}/{filename}")
        if current is None:
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        stem = filename.rsplit(".", 1)[0]
        path = f"{year}/backups/{stem}-{stamp}.csv"
        self._store.write(path, current)
        return path

    def commit_students(self, year: str, students: Sequence[Student]) -> str | None:
        """Replace the whole student roster of ``year``, backing up the previous one.

        Args:
            year: Target academic year.
            students: Students to write, all levels, already identified.

        Returns:
            The path of the backup written, or ``None`` if there was no
            previous file.
        """
        backup = self._backup(year, STUDENTS_FILE)
        ordered = sorted(students, key=lambda s: (s.level, s.name))
        self._store.write(f"{year}/{STUDENTS_FILE}", students_to_csv(ordered))
        return backup

    def commit_students_for_level(
        self, year: str, level: str, students: Sequence[Student]
    ) -> str | None:
        """Replace the students of one level, leaving the other untouched.

        The two promotions are managed on different schedules -- M2 is known
        early, M1 keeps moving until October -- so importing one must never
        disturb the other.

        Args:
            year: Target academic year.
            level: Level being replaced.
            students: Students of that level, already identified.

        Returns:
            The path of the backup written, or ``None`` if there was no
            previous file.
        """
        others = [s for s in self.load_students(year) if s.level != level]
        return self.commit_students(year, [*others, *students])

    def replace_level_from_editor(
        self, year: str, level: str, names: Sequence[str]
    ) -> tuple[str | None, list[Student]]:
        """Rebuild one level from a list of names typed in the interface.

        Students already present keep their identifier; new names receive the
        next free one.

        Args:
            year: Target academic year.
            level: Level being edited.
            names: Display names, in any order; blanks are ignored.

        Returns:
            The backup path and the resulting students of that level.
        """
        previous = [s for s in self.load_students(year) if s.level == level]
        drafts = [
            Student(student_id="", name=" ".join(name.split()), level=level, academic_year=year)
            for name in names
            if str(name).strip()
        ]
        resolved = self._allocate_ids(drafts, previous)
        backup = self.commit_students_for_level(year, level, resolved)
        return backup, resolved

    def commit_courses(self, year: str, courses: Sequence[Course]) -> str | None:
        """Replace the course list of ``year``, backing up the previous one."""
        backup = self._backup(year, COURSES_FILE)
        self._store.write(f"{year}/{COURSES_FILE}", courses_to_csv(courses))
        return backup

    # ------------------------------------------------------------------
    # Backups
    # ------------------------------------------------------------------

    def list_backups(self, year: str) -> list[str]:
        """Return the backup paths available for ``year``, most recent first."""
        return sorted(self._store.list(f"{year}/backups"), reverse=True)

    def restore_backup(self, backup_path: str, year: str) -> None:
        """Restore a backup over the current file.

        Args:
            backup_path: Path returned by :meth:`list_backups`.
            year: Academic year the backup belongs to.

        Raises:
            FileNotFoundError: If the backup no longer exists.
            ValueError: If the backup name is not recognised.
        """
        data = self._store.read(backup_path)
        if data is None:
            raise FileNotFoundError(backup_path)

        name = backup_path.rsplit("/", 1)[-1]
        if name.startswith("students-"):
            target = STUDENTS_FILE
        elif name.startswith("courses-"):
            target = COURSES_FILE
        else:
            raise ValueError(f"Unrecognised backup file: {name}")

        self._backup(year, target)
        self._store.write(f"{year}/{target}", data)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_students(self, year: str) -> bytes:
        """Return the student roster of ``year`` as canonical CSV bytes."""
        return students_to_csv(self.load_students(year))

    def export_courses(self, year: str) -> bytes:
        """Return the course list of ``year`` as canonical CSV bytes."""
        return courses_to_csv(self.load_courses(year))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_roster_store(settings: Settings | None = None) -> RosterStore:
    """Build the roster store described by the configuration.

    Args:
        settings: Application settings; loaded from secrets when omitted.

    Returns:
        A :class:`RosterStore` implementation.
    """
    settings = settings or get_settings()
    if settings.roster.backend == "local":
        return LocalRosterStore(settings.roster.local_dir)

    from supabase import create_client

    client = create_client(settings.supabase.url, settings.supabase.service_key)
    return SupabaseRosterStore(client, settings.roster.bucket)


def build_roster_service(settings: Settings | None = None) -> RosterService:
    """Build a :class:`RosterService` from the configuration."""
    return RosterService(build_roster_store(settings))
