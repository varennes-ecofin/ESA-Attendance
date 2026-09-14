#!/usr/bin/env python3
"""Convert the legacy hard-coded roster into the new CSV files.

The previous version stored courses and students as Python dictionaries in
``utils/courses.py``. This one-shot script reads that module and writes the two
canonical CSV files, so that the course list does not have to be retyped and
last year's roster can be archived before the new promotions are imported.

Usage::

    python scripts/export_legacy_roster.py --year 2025-2026 --out data/roster

Then, from the admin page, upload ``courses.csv`` for the new academic year
(the course catalogue rarely changes) and the two new promotion files.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from esa_attendance.roster.csv_io import courses_to_csv, students_to_csv  # noqa: E402
from esa_attendance.roster.models import Course, Student  # noqa: E402

EXCLUDED_COURSE_CODES = {"ESA_MAINTENANCE"}


def load_legacy_module(path: Path) -> ModuleType:
    """Import ``utils/courses.py`` by file path.

    Args:
        path: Path to the legacy module.

    Returns:
        The imported module.

    Raises:
        FileNotFoundError: If the module does not exist.
        ImportError: If the module cannot be loaded.
    """
    if not path.is_file():
        raise FileNotFoundError(path)

    spec = importlib.util.spec_from_file_location("legacy_courses", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_courses(module: ModuleType) -> list[Course]:
    """Build :class:`Course` objects from the legacy ``COURSES`` dictionary."""
    courses: list[Course] = []
    for code, info in module.COURSES.items():
        if code in EXCLUDED_COURSE_CODES or info.get("year") not in ("M1", "M2"):
            continue
        courses.append(
            Course(code=code, name=info["name"], level=info["year"], active=True)
        )
    return sorted(courses, key=lambda c: (c.level, c.code))


def extract_students(module: ModuleType, academic_year: str) -> list[Student]:
    """Build :class:`Student` objects from the legacy ``STUDENTS_BY_YEAR`` mapping."""
    students: list[Student] = []
    for level, entries in module.STUDENTS_BY_YEAR.items():
        if level not in ("M1", "M2"):
            continue
        for entry in entries:
            students.append(
                Student(
                    student_id=str(entry["id"]).strip(),
                    name=" ".join(str(entry["name"]).split()),
                    level=level,
                    academic_year=academic_year,
                )
            )
    return sorted(students, key=lambda s: (s.level, s.name))


def main() -> int:
    """Entry point.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--legacy",
        type=Path,
        default=REPO_ROOT / "utils" / "courses.py",
        help="Path to the legacy utils/courses.py module",
    )
    parser.add_argument(
        "--year",
        required=True,
        help="Academic year the exported roster belongs to, e.g. 2025-2026",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "roster",
        help="Output directory; files are written under <out>/<year>/",
    )
    args = parser.parse_args()

    module = load_legacy_module(args.legacy)
    courses = extract_courses(module)
    students = extract_students(module, args.year)

    target = args.out / args.year
    target.mkdir(parents=True, exist_ok=True)
    (target / "courses.csv").write_bytes(courses_to_csv(courses))
    (target / "students.csv").write_bytes(students_to_csv(students))

    per_level = {
        level: sum(1 for s in students if s.level == level) for level in ("M1", "M2")
    }
    print(f"Wrote {len(courses)} courses to {target / 'courses.csv'}")
    print(
        f"Wrote {len(students)} students to {target / 'students.csv'} "
        f"(M1: {per_level['M1']}, M2: {per_level['M2']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
