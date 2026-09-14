#!/usr/bin/env python3
"""Copy roster files between the local directory and the Supabase bucket.

Used when switching backends: the files themselves are identical, only their
storage differs, so re-importing them through the interface would be pointless
work and a chance to pick the wrong level.

Usage::

    # local disk -> Supabase bucket (before deployment)
    python scripts/sync_roster.py --to supabase

    # Supabase bucket -> local disk (to work offline on production data)
    python scripts/sync_roster.py --to local --year 2026-2027

Both endpoints are read from the secrets: ``[supabase]`` for the credentials,
``[roster] local_dir`` and ``[roster] bucket`` for the two locations. The
``backend`` setting is ignored here -- this script always sees both.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from supabase import create_client  # noqa: E402

from esa_attendance.config import get_settings  # noqa: E402
from esa_attendance.roster.models import is_valid_academic_year  # noqa: E402
from esa_attendance.roster.service import (  # noqa: E402
    COURSES_FILE,
    MANIFEST_PATH,
    STUDENTS_FILE,
)
from esa_attendance.roster.store import (  # noqa: E402
    LocalRosterStore,
    RosterStore,
    SupabaseRosterStore,
)


def build_stores() -> tuple[LocalRosterStore, SupabaseRosterStore]:
    """Build both stores from the configuration.

    Returns:
        The local store and the Supabase store.
    """
    settings = get_settings()
    local = LocalRosterStore(settings.roster.local_dir)
    client = create_client(settings.supabase.url, settings.supabase.service_key)
    remote = SupabaseRosterStore(client, settings.roster.bucket)
    return local, remote


def discover_years(local: LocalRosterStore, explicit: str | None) -> list[str]:
    """Return the years to copy.

    Args:
        local: Local store, used to enumerate years when none is given.
        explicit: Year passed on the command line, if any.

    Returns:
        The list of academic years.

    Raises:
        ValueError: If the explicit year is malformed.
    """
    if explicit:
        if not is_valid_academic_year(explicit):
            raise ValueError(f"Année invalide : {explicit!r} (format attendu 2026-2027)")
        return [explicit]

    base = Path(get_settings().roster.local_dir)
    if not base.is_dir():
        return []
    return sorted(
        item.name for item in base.iterdir()
        if item.is_dir() and is_valid_academic_year(item.name)
    )


def copy(source: RosterStore, target: RosterStore, paths: list[str]) -> int:
    """Copy the given paths from one store to the other.

    Args:
        source: Store to read from.
        target: Store to write to.
        paths: Paths to copy; missing ones are skipped with a message.

    Returns:
        The number of files actually copied.
    """
    copied = 0
    for path in paths:
        data = source.read(path)
        if data is None:
            print(f"  absent, ignoré : {path}")
            continue
        target.write(path, data)
        print(f"  copié : {path} ({len(data)} octets)")
        copied += 1
    return copied


def main() -> int:
    """Entry point.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to",
        required=True,
        choices=["supabase", "local"],
        help="Destination de la copie",
    )
    parser.add_argument(
        "--year",
        default=None,
        help="Année à copier ; par défaut, toutes celles présentes en local",
    )
    args = parser.parse_args()

    local, remote = build_stores()
    source, target = (local, remote) if args.to == "supabase" else (remote, local)

    years = discover_years(local, args.year)
    if not years:
        print("Aucune année trouvée. Précisez --year.")
        return 1

    paths = [MANIFEST_PATH]
    for year in years:
        paths += [f"{year}/{STUDENTS_FILE}", f"{year}/{COURSES_FILE}"]

    print(f"Copie vers {args.to} — années : {', '.join(years)}")
    copied = copy(source, target, paths)
    print(f"{copied} fichier(s) copié(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
