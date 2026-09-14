"""Streamlit login form and role gating."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import streamlit as st

from ..auth import Role, authenticate

SESSION_KEY = "esa_user"
SESSION_MAX_AGE = timedelta(hours=12)
LOGO_URL = (
    "https://raw.githubusercontent.com/varennes-ecofin/ESA-Attendance/"
    "main/data/ESALogoNewWebLightBG-02.png"
)


@dataclass(frozen=True)
class User:
    """The authenticated user held in the Streamlit session state."""

    username: str
    role: Role
    logged_in_at: str

    @property
    def is_admin(self) -> bool:
        """Return True when the user may access the administration pages."""
        return self.role == "admin"


def _credentials() -> tuple[dict[str, str], dict[str, str]]:
    """Read the ``[teachers]`` and ``[admins]`` tables from the secrets."""
    teachers = dict(st.secrets.get("teachers", {}))
    admins = dict(st.secrets.get("admins", {}))
    return (
        {k: str(v) for k, v in teachers.items()},
        {k: str(v) for k, v in admins.items()},
    )


def current_user() -> User | None:
    """Return the logged-in user, or ``None`` if absent or expired."""
    payload = st.session_state.get(SESSION_KEY)
    if not isinstance(payload, dict):
        return None

    try:
        user = User(**payload)
        logged_in_at = datetime.fromisoformat(user.logged_in_at)
    except (TypeError, ValueError):
        st.session_state.pop(SESSION_KEY, None)
        return None

    if datetime.now(timezone.utc) - logged_in_at > SESSION_MAX_AGE:
        st.session_state.pop(SESSION_KEY, None)
        return None
    return user


def logout() -> None:
    """Clear the session and rerun."""
    st.session_state.pop(SESSION_KEY, None)
    st.rerun()


def render_user_box() -> None:
    """Show the current user and a logout button in the sidebar."""
    user = current_user()
    if user is None:
        return
    with st.sidebar:
        st.markdown("---")
        label = "administrateur" if user.is_admin else "enseignant"
        st.markdown(f"**👤 {user.username}** — {label}")
        if st.button("🚪 Déconnexion", width="stretch"):
            logout()


def login_form() -> None:
    """Render the login form and store the session on success."""
    st.markdown(
        f"<div style='text-align:center;padding:1rem 0'>"
        f"<img src='{LOGO_URL}' style='max-width:420px;width:100%;height:auto'></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='text-align:center'><h2>ESA Attendance</h2></div>",
        unsafe_allow_html=True,
    )

    _, middle, _ = st.columns([1, 2, 1])
    with middle, st.form("login_form"):
        st.markdown("#### 🔐 Connexion")
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", width="stretch")

    if not submitted:
        return

    teachers, admins = _credentials()
    if not teachers and not admins:
        st.error(
            "Aucun compte configuré. Ajoutez une section [teachers] ou [admins] "
            "dans les secrets de l'application."
        )
        return

    result = authenticate(username, password, teachers, admins)
    if result is None:
        st.error("Identifiant ou mot de passe incorrect.")
        return

    user = User(
        username=result.username,
        role=result.role,
        logged_in_at=datetime.now(timezone.utc).isoformat(),
    )
    st.session_state[SESSION_KEY] = asdict(user)

    if result.needs_rehash:
        st.session_state["password_needs_rehash"] = True
    st.rerun()


def require_role(*allowed: Role) -> User:
    """Ensure the visitor is logged in with one of the allowed roles.

    Renders the login form (or an access-denied message) and stops the script
    when the requirement is not met.

    Args:
        *allowed: Roles granting access; defaults to any authenticated role.

    Returns:
        The authenticated :class:`User`.
    """
    user = current_user()
    if user is None:
        login_form()
        st.stop()

    if allowed and user.role not in allowed:
        st.error("Cette page est réservée aux administrateurs.")
        st.stop()

    if st.session_state.get("password_needs_rehash"):
        st.warning(
            "Votre mot de passe est encore stocké avec l'ancien algorithme. "
            "Regénérez son empreinte avec "
            "`python -m esa_attendance.auth \"nouveau mot de passe\"`.",
            icon="⚠️",
        )
    return user
