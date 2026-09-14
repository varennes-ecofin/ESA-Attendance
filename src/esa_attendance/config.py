"""Application configuration.

Settings are read once from Streamlit secrets, with environment variables as a
fallback so that maintenance scripts and tests can run outside Streamlit.

The only value that a non-technical user needs to change at runtime -- the
current academic year -- is deliberately NOT stored here: it lives in the
roster manifest (see ``esa_attendance.roster.service``) so that the registrar
can switch year from the admin page without touching any secret file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

RosterBackend = Literal["supabase", "local"]


class ConfigError(RuntimeError):
    """Raised when a mandatory setting is missing or malformed."""


# -----------------------------------------------------------------------------
# Secret access
# -----------------------------------------------------------------------------

def _to_plain(value: Any) -> Any:
    """Recursively convert Streamlit secret objects into plain containers.

    ``st.secrets`` returns ``AttrDict`` instances for TOML sections. They
    implement ``Mapping`` but do not subclass ``dict``, so any ``isinstance(...,
    dict)`` test downstream would silently fail and the section would look
    absent.

    Args:
        value: A secrets object, section, list or scalar.

    Returns:
        The same structure built from plain ``dict`` and ``list`` objects.
    """
    if isinstance(value, Mapping):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


def _secrets() -> dict[str, Any]:
    """Return Streamlit secrets as plain nested dictionaries, or an empty one.

    Streamlit is imported lazily so that this module stays usable in scripts
    and unit tests that never start a Streamlit runtime.
    """
    try:
        import streamlit as st

        return _to_plain(st.secrets)
    except Exception:  # noqa: BLE001 -- no Streamlit runtime, or no secrets file
        return {}


def _get(secrets: dict[str, Any], section: str, key: str, env: str,
         default: str | None = None) -> str | None:
    """Look up ``section.key`` in secrets, then ``env`` in the environment."""
    value = secrets.get(section, {})
    if isinstance(value, dict) and key in value:
        return str(value[key])
    return os.environ.get(env, default)


def _require(value: str | None, name: str) -> str:
    """Return ``value`` or raise a :class:`ConfigError` naming the setting."""
    if not value:
        raise ConfigError(
            f"Missing configuration: {name}. "
            "Add it to .streamlit/secrets.toml or to the environment."
        )
    return value


# -----------------------------------------------------------------------------
# Settings
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SupabaseSettings:
    """Credentials for the two Supabase roles used by the application."""

    url: str
    anon_key: str
    service_key: str


@dataclass(frozen=True)
class RosterSettings:
    """Where the student and course CSV files are stored.

    Attributes:
        backend: ``"supabase"`` for Supabase Storage (mandatory in production,
            since the Streamlit Cloud filesystem is ephemeral), ``"local"`` for
            a directory on disk during development.
        bucket: Name of the private Supabase Storage bucket.
        local_dir: Directory used when ``backend == "local"``.
    """

    backend: RosterBackend
    bucket: str
    local_dir: str


@dataclass(frozen=True)
class EmailSettings:
    """SMTP configuration for the attendance report."""

    sender: str
    password: str
    smtp_server: str
    smtp_port: int
    recipients: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    """Full application configuration."""

    base_url: str
    supabase: SupabaseSettings
    roster: RosterSettings
    email: EmailSettings | None


def _parse_recipients(raw: Any) -> tuple[str, ...]:
    """Accept either a TOML list or a comma-separated string."""
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(r).strip() for r in raw if str(r).strip())
    return tuple(part.strip() for part in str(raw).split(",") if part.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build and cache the :class:`Settings` object.

    Returns:
        The application settings.

    Raises:
        ConfigError: If a mandatory Supabase setting is missing.
    """
    secrets = _secrets()

    supabase = SupabaseSettings(
        url=_require(_get(secrets, "supabase", "url", "SUPABASE_URL"), "supabase.url"),
        anon_key=_require(
            _get(secrets, "supabase", "key", "SUPABASE_ANON_KEY"), "supabase.key"
        ),
        service_key=_require(
            _get(secrets, "supabase", "service_key", "SUPABASE_SERVICE_KEY"),
            "supabase.service_key",
        ),
    )

    roster_backend = (
        _get(secrets, "roster", "backend", "ESA_ROSTER_BACKEND", "supabase") or "supabase"
    ).lower()
    if roster_backend not in ("supabase", "local"):
        raise ConfigError(f"roster.backend must be 'supabase' or 'local', got {roster_backend!r}")

    roster = RosterSettings(
        backend=roster_backend,  # type: ignore[arg-type]
        bucket=_get(secrets, "roster", "bucket", "ESA_ROSTER_BUCKET", "roster") or "roster",
        local_dir=_get(secrets, "roster", "local_dir", "ESA_ROSTER_DIR", "data/roster")
        or "data/roster",
    )

    email_section = secrets.get("email", {}) if isinstance(secrets.get("email"), dict) else {}
    email: EmailSettings | None = None
    if email_section.get("sender"):
        email = EmailSettings(
            sender=str(email_section["sender"]),
            password=str(email_section.get("password", "")),
            smtp_server=str(email_section.get("smtp_server", "smtp.gmail.com")),
            smtp_port=int(email_section.get("smtp_port", 587)),
            recipients=_parse_recipients(email_section.get("recipient_email")),
        )

    return Settings(
        base_url=str(secrets.get("base_url", os.environ.get("ESA_BASE_URL", ""))).rstrip("/"),
        supabase=supabase,
        roster=roster,
        email=email,
    )
