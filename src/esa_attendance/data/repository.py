"""Supabase access layer.

All database traffic goes through :class:`AttendanceRepository`. Three points
deserve attention:

* **Pagination.** PostgREST caps a response at 1000 rows. Any query that can
  exceed that (a full-year export) is paginated through ``.range()``; silently
  truncated exports were a latent bug in the previous version.
* **Check-in.** Students no longer read the ``attendance_records`` table to
  detect duplicates: the whole operation is a single ``check_in`` RPC executed
  with definer rights, which allowed the public SELECT policy to be dropped.
* **Statistics.** The per-session loops are replaced by the two aggregation
  views created in ``sql/001_rollover_and_hardening.sql``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal

import pandas as pd
from supabase import Client, create_client

from ..config import get_settings

ClientRole = Literal["anon", "service"]
PAGE_SIZE = 1000

_CHECK_IN_MESSAGES: dict[str, str] = {
    "unknown_session": "Cette session n'existe pas.",
    "session_closed": "La session est fermée : l'appel est terminé.",
    "already_checked_in": "Votre présence est déjà enregistrée.",
    "invalid_student": "Sélection invalide, merci de recommencer.",
}


@lru_cache(maxsize=2)
def get_client(role: ClientRole = "service") -> Client:
    """Return a cached Supabase client for the given role.

    Args:
        role: ``"anon"`` for the public student page, ``"service"`` for the
            authenticated teacher and admin pages.

    Returns:
        A configured Supabase client.
    """
    settings = get_settings()
    key = (
        settings.supabase.service_key if role == "service" else settings.supabase.anon_key
    )
    return create_client(settings.supabase.url, key)


@dataclass(frozen=True)
class CheckInResult:
    """Outcome of a student check-in attempt."""

    ok: bool
    reason: str = ""

    @property
    def message(self) -> str:
        """Return a message suitable for display to the student."""
        if self.ok:
            return "Présence enregistrée."
        return _CHECK_IN_MESSAGES.get(self.reason, f"Échec de l'enregistrement ({self.reason}).")


class AttendanceRepository:
    """Read and write attendance sessions and records."""

    def __init__(self, client: Client) -> None:
        """Initialize the repository.

        Args:
            client: Supabase client; use the service role for teacher and
                admin features, the anon role for the public page.
        """
        self._db = client

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_all(
        self,
        table: str,
        columns: str,
        *,
        eq: dict[str, Any] | None = None,
        order_by: str = "id",
    ) -> list[dict[str, Any]]:
        """Fetch every matching row, paginating around the PostgREST row cap.

        Args:
            table: Table or view name.
            columns: PostgREST column selection.
            eq: Equality filters applied to the query.
            order_by: Column used to keep pagination stable.

        Returns:
            The complete list of rows.
        """
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            query = self._db.table(table).select(columns)
            for column, value in (eq or {}).items():
                query = query.eq(column, value)
            result = query.order(order_by).range(offset, offset + PAGE_SIZE - 1).execute()
            batch = result.data or []
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                return rows
            offset += PAGE_SIZE

    def _count(self, table: str, **eq: Any) -> int:
        """Return an exact row count without transferring the rows."""
        query = self._db.table(table).select("id", count="exact")
        for column, value in eq.items():
            query = query.eq(column, value)
        result = query.limit(1).execute()
        return int(result.count or 0)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self, session_id: str, course_code: str, teacher_username: str, academic_year: str
    ) -> None:
        """Open a new attendance session.

        The academic year is passed explicitly rather than left to the database
        trigger, so that the roster manifest remains the single source of truth
        for which year is running.

        Args:
            session_id: Unique session identifier.
            course_code: Course the session belongs to.
            teacher_username: Owner of the session.
            academic_year: Active academic year, e.g. ``"2026-2027"``.
        """
        self._db.table("attendance_sessions").insert(
            {
                "session_id": session_id,
                "course_code": course_code,
                "teacher_username": teacher_username,
                "academic_year": academic_year,
                "status": "active",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": None,
            }
        ).execute()

    def close_session(self, session_id: str) -> None:
        """Close an open session."""
        self._db.table("attendance_sessions").update(
            {"status": "closed", "ended_at": datetime.now(timezone.utc).isoformat()}
        ).eq("session_id", session_id).execute()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return a session row, or ``None`` when it does not exist.

        With the anon client the row is returned only while the session is
        active, which is exactly the visibility a student needs.
        """
        result = (
            self._db.table("attendance_sessions")
            .select("*")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def teacher_sessions(self, teacher_username: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return the most recent sessions opened by a teacher."""
        result = (
            self._db.table("attendance_sessions")
            .select("session_id, course_code, status, started_at")
            .eq("teacher_username", teacher_username)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def close_stale_sessions(self, older_than_hours: int = 12) -> int:
        """Close sessions left open by a crashed browser or a forgotten tab.

        Args:
            older_than_hours: Minimum age, in hours, before a session is
                considered abandoned.

        Returns:
            The number of sessions closed.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
        result = (
            self._db.table("attendance_sessions")
            .update({"status": "closed", "ended_at": datetime.now(timezone.utc).isoformat()})
            .eq("status", "active")
            .lt("started_at", cutoff)
            .execute()
        )
        return len(result.data or [])

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------

    def check_in(self, session_id: str, student_id: str, student_name: str) -> CheckInResult:
        """Record a student's presence through the ``check_in`` RPC.

        Args:
            session_id: Target session.
            student_id: Roster identifier of the student.
            student_name: Display name stored alongside the record.

        Returns:
            The outcome, including a displayable reason on failure.
        """
        try:
            response = self._db.rpc(
                "check_in",
                {
                    "p_session_id": session_id,
                    "p_student_id": student_id,
                    "p_student_name": student_name,
                },
            ).execute()
        except Exception as exc:  # noqa: BLE001 -- surfaced to the student
            return CheckInResult(ok=False, reason=f"rpc_error: {exc}")

        payload = response.data or {}
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict):
            return CheckInResult(ok=False, reason="unexpected_response")
        return CheckInResult(ok=bool(payload.get("ok")), reason=str(payload.get("reason", "")))

    def session_records(self, session_id: str) -> list[dict[str, Any]]:
        """Return every attendance record of a session, oldest first."""
        result = (
            self._db.table("attendance_records")
            .select("student_id, student_name, checked_in_at")
            .eq("session_id", session_id)
            .order("checked_in_at")
            .execute()
        )
        return result.data or []

    def session_attendance_frame(self, session_id: str) -> pd.DataFrame:
        """Return the live attendance list, formatted for display."""
        records = self.session_records(session_id)
        if not records:
            return pd.DataFrame(columns=["Étudiant", "Heure"])
        return pd.DataFrame(
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

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def course_stats(self, academic_year: str) -> pd.DataFrame:
        """Return per-course statistics for a year, in a single query."""
        result = (
            self._db.table("course_attendance_stats")
            .select("*")
            .eq("academic_year", academic_year)
            .execute()
        )
        columns = ["academic_year", "course_code", "num_sessions", "total_checkins", "avg_per_session"]
        return pd.DataFrame(result.data or [], columns=columns)

    def attendance_detail(self, academic_year: str) -> pd.DataFrame:
        """Return one row per (closed session, student) for a whole year."""
        rows = self._fetch_all(
            "attendance_detail",
            "academic_year, session_id, course_code, started_at, student_id, student_name",
            eq={"academic_year": academic_year},
            order_by="session_id",
        )
        columns = [
            "academic_year", "session_id", "course_code",
            "started_at", "student_id", "student_name",
        ]
        return pd.DataFrame(rows, columns=columns)

    # ------------------------------------------------------------------
    # Archiving
    # ------------------------------------------------------------------

    def year_summary(self) -> pd.DataFrame:
        """Return the volume of data held per academic year.

        Returns:
            A DataFrame with columns ``academic_year``, ``sessions``,
            ``records``, sorted by descending year.
        """
        sessions = self._fetch_all("attendance_sessions", "academic_year")
        if not sessions:
            return pd.DataFrame(columns=["academic_year", "sessions", "records"])

        counts = pd.Series([row["academic_year"] for row in sessions]).value_counts()
        rows = [
            {
                "academic_year": year,
                "sessions": int(counts[year]),
                "records": self._count("attendance_records", academic_year=year),
            }
            for year in counts.index
        ]
        return pd.DataFrame(rows).sort_values("academic_year", ascending=False).reset_index(drop=True)

    def export_year(self, academic_year: str) -> pd.DataFrame:
        """Return the complete archive of a year, sessions without attendance included.

        Args:
            academic_year: Year to export.

        Returns:
            One row per (session, student), with a single row carrying empty
            student columns for sessions where nobody checked in.
        """
        sessions = pd.DataFrame(
            self._fetch_all(
                "attendance_sessions",
                "session_id, course_code, teacher_username, status, started_at, ended_at, academic_year",
                eq={"academic_year": academic_year},
            )
        )
        if sessions.empty:
            return pd.DataFrame()

        records = pd.DataFrame(
            self._fetch_all(
                "attendance_records",
                "session_id, student_id, student_name, checked_in_at",
                eq={"academic_year": academic_year},
            )
        )
        if records.empty:
            records = pd.DataFrame(
                columns=["session_id", "student_id", "student_name", "checked_in_at"]
            )

        merged = sessions.merge(records, on="session_id", how="left")
        return merged.sort_values(["started_at", "student_name"], na_position="last")

    @staticmethod
    def to_archive_csv(frame: pd.DataFrame) -> bytes:
        """Serialize an archive with a BOM so Excel opens accents correctly."""
        return frame.to_csv(index=False).encode("utf-8-sig")

    def purge_year(self, academic_year: str) -> dict[str, Any]:
        """Delete every session and record of a past year.

        Args:
            academic_year: Year to purge, formatted ``YYYY-YYYY``.

        Returns:
            The counters returned by the ``purge_academic_year`` RPC.

        Raises:
            RuntimeError: If the RPC fails or returns an unexpected payload.
        """
        try:
            response = self._db.rpc(
                "purge_academic_year", {"p_year": academic_year}
            ).execute()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Purge failed for {academic_year}: {exc}") from exc

        payload = response.data
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected purge response: {payload!r}")
        return payload
