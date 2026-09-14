"""Storage backends for the roster files.

Two implementations share one interface:

``LocalRosterStore``
    A plain directory. Convenient for development and for a self-hosted
    deployment with a persistent volume.

``SupabaseRosterStore``
    A private Supabase Storage bucket. Mandatory on Streamlit Cloud, whose
    filesystem is reset on every restart or redeploy: a CSV uploaded by the
    registrar and written to disk would silently disappear.

Bucket setup (once, in the Supabase dashboard):
    Storage > New bucket > name ``roster``, "Public bucket" **unchecked**.
    No storage policy is required: the application accesses it with the
    service role, which bypasses row-level security.
"""

from __future__ import annotations

import abc
from pathlib import Path

from supabase import Client


class RosterStoreError(RuntimeError):
    """Raised when a roster file cannot be read or written."""


class RosterStore(abc.ABC):
    """Key-value store for roster files, keyed by a POSIX-like path."""

    @abc.abstractmethod
    def read(self, path: str) -> bytes | None:
        """Return the content of ``path``, or ``None`` if it does not exist."""

    @abc.abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Create or overwrite ``path`` with ``data``."""

    @abc.abstractmethod
    def list(self, prefix: str) -> list[str]:
        """Return the paths stored directly under ``prefix``, sorted."""

    @abc.abstractmethod
    def delete(self, path: str) -> None:
        """Remove ``path`` if it exists."""


# -----------------------------------------------------------------------------
# Local filesystem
# -----------------------------------------------------------------------------

class LocalRosterStore(RosterStore):
    """Store roster files under a base directory on the local filesystem."""

    def __init__(self, base_dir: str | Path) -> None:
        """Initialize the store.

        Args:
            base_dir: Directory holding the roster tree. Created on demand.
        """
        self._base = Path(base_dir)

    def _resolve(self, path: str) -> Path:
        """Return the absolute path of ``path``, rejecting directory escapes."""
        target = (self._base / path).resolve()
        base = self._base.resolve()
        if base not in target.parents and target != base:
            raise RosterStoreError(f"Path outside of the roster directory: {path}")
        return target

    def read(self, path: str) -> bytes | None:
        """Return the content of ``path``, or ``None`` if absent."""
        target = self._resolve(path)
        if not target.is_file():
            return None
        return target.read_bytes()

    def write(self, path: str, data: bytes) -> None:
        """Create or overwrite ``path``."""
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def list(self, prefix: str) -> list[str]:
        """Return the file paths directly under ``prefix``."""
        directory = self._resolve(prefix)
        if not directory.is_dir():
            return []
        return sorted(
            f"{prefix.rstrip('/')}/{item.name}"
            for item in directory.iterdir()
            if item.is_file()
        )

    def delete(self, path: str) -> None:
        """Remove ``path`` if it exists."""
        target = self._resolve(path)
        if target.is_file():
            target.unlink()


# -----------------------------------------------------------------------------
# Supabase Storage
# -----------------------------------------------------------------------------

def _is_not_found(exc: Exception) -> bool:
    """Return True when a storage exception means "object does not exist"."""
    message = str(exc).lower()
    return "not found" in message or "404" in message or "does not exist" in message


class SupabaseRosterStore(RosterStore):
    """Store roster files in a private Supabase Storage bucket."""

    def __init__(self, client: Client, bucket: str = "roster") -> None:
        """Initialize the store.

        Args:
            client: Supabase client created with the **service** key.
            bucket: Name of the private bucket.
        """
        self._client = client
        self._bucket = bucket

    @property
    def _api(self):  # noqa: ANN202 -- storage3 client, untyped upstream
        """Return the storage API bound to the configured bucket."""
        return self._client.storage.from_(self._bucket)

    def read(self, path: str) -> bytes | None:
        """Return the content of ``path``, or ``None`` if absent."""
        try:
            return bytes(self._api.download(path))
        except Exception as exc:  # noqa: BLE001 -- storage3 raises broad errors
            if _is_not_found(exc):
                return None
            raise RosterStoreError(f"Cannot read {path}: {exc}") from exc

    def write(self, path: str, data: bytes) -> None:
        """Create or overwrite ``path``.

        ``upsert`` must be passed as a string: it becomes an HTTP header.
        """
        options = {"content-type": "text/csv; charset=utf-8", "upsert": "true"}
        try:
            self._api.upload(path=path, file=data, file_options=options)
        except Exception as exc:  # noqa: BLE001
            try:
                self._api.update(path=path, file=data, file_options=options)
            except Exception as inner:  # noqa: BLE001
                raise RosterStoreError(f"Cannot write {path}: {exc} / {inner}") from inner

    def list(self, prefix: str) -> list[str]:
        """Return the object paths directly under ``prefix``."""
        try:
            entries = self._api.list(path=prefix.rstrip("/"))
        except Exception as exc:  # noqa: BLE001
            if _is_not_found(exc):
                return []
            raise RosterStoreError(f"Cannot list {prefix}: {exc}") from exc

        names = [
            entry["name"]
            for entry in entries or []
            if isinstance(entry, dict) and entry.get("name")
        ]
        # Supabase inserts a hidden placeholder in empty folders.
        return sorted(
            f"{prefix.rstrip('/')}/{name}"
            for name in names
            if name != ".emptyFolderPlaceholder"
        )

    def delete(self, path: str) -> None:
        """Remove ``path`` if it exists."""
        try:
            self._api.remove([path])
        except Exception as exc:  # noqa: BLE001
            if not _is_not_found(exc):
                raise RosterStoreError(f"Cannot delete {path}: {exc}") from exc
