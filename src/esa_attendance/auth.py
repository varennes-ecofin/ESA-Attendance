"""Password hashing and role resolution.

The previous scheme was a single unsalted-per-user SHA-256 with a constant salt
written in the source: fast to compute, therefore fast to brute-force. This
module uses bcrypt, while still accepting the legacy hashes so that existing
credentials keep working; ``AuthResult.needs_rehash`` flags the accounts that
should be re-issued.

No Streamlit import here, so the logic stays testable and usable from scripts::

    python -m esa_attendance.auth "un mot de passe"
"""

from __future__ import annotations

import hashlib
import hmac
import sys
from dataclasses import dataclass
from typing import Literal, Mapping

import bcrypt

Role = Literal["teacher", "admin"]

LEGACY_SALT = "esa_attendance_salt"
BCRYPT_ROUNDS = 12
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_BCRYPT_MAX_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds the 72-byte bcrypt input limit."""


@dataclass(frozen=True)
class AuthResult:
    """A successful authentication.

    Attributes:
        username: Authenticated user.
        role: ``"admin"`` grants the roster and maintenance pages on top of
            everything a teacher can do.
        needs_rehash: True when the stored hash uses the legacy algorithm.
    """

    username: str
    role: Role
    needs_rehash: bool = False


def hash_password(password: str) -> str:
    """Hash a password with bcrypt.

    Args:
        password: Plain-text password.

    Returns:
        The bcrypt hash, ready to be pasted into ``secrets.toml``.

    Raises:
        PasswordTooLongError: If the password exceeds 72 bytes once encoded.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise PasswordTooLongError(
            f"bcrypt accepts at most {_BCRYPT_MAX_BYTES} bytes, got {len(encoded)}"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def _legacy_hash(password: str) -> str:
    """Reproduce the historical SHA-256 hash for backward compatibility."""
    return hashlib.sha256(f"{password}{LEGACY_SALT}".encode()).hexdigest()


def verify_password(stored_hash: str, password: str) -> tuple[bool, bool]:
    """Verify a password against a stored hash of either generation.

    Args:
        stored_hash: Hash read from the secrets file.
        password: Plain-text password submitted by the user.

    Returns:
        A tuple ``(is_valid, needs_rehash)``.
    """
    stored_hash = stored_hash.strip()
    if stored_hash.startswith(_BCRYPT_PREFIXES):
        encoded = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        try:
            return bcrypt.checkpw(encoded, stored_hash.encode("ascii")), False
        except ValueError:
            return False, False

    if len(stored_hash) == 64:  # legacy hex SHA-256
        return hmac.compare_digest(stored_hash, _legacy_hash(password)), True

    return False, False


def authenticate(
    username: str,
    password: str,
    teachers: Mapping[str, str],
    admins: Mapping[str, str] | None = None,
) -> AuthResult | None:
    """Authenticate a user against the configured credential tables.

    A username listed in ``admins`` is resolved as an administrator, whatever
    the ``teachers`` table says.

    Args:
        username: Submitted username.
        password: Submitted password.
        teachers: Mapping of teacher username to password hash.
        admins: Mapping of administrator username to password hash.

    Returns:
        The :class:`AuthResult` on success, ``None`` otherwise.
    """
    username = username.strip()
    if not username or not password:
        return None

    for table, role in ((admins or {}, "admin"), (teachers, "teacher")):
        stored = table.get(username)
        if stored is None:
            continue
        valid, needs_rehash = verify_password(str(stored), password)
        if valid:
            return AuthResult(username=username, role=role, needs_rehash=needs_rehash)  # type: ignore[arg-type]
        return None  # username found but wrong password: stop here

    return None


def _main(argv: list[str]) -> int:
    """Print a bcrypt hash for the password given on the command line."""
    if len(argv) != 2:
        print('Usage: python -m esa_attendance.auth "password"', file=sys.stderr)
        return 2
    print(hash_password(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
