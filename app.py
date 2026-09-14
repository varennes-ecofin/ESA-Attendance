"""ESA Attendance -- application entry point.

Run with::

    streamlit run app.py

Two routes share this file. ``?mode=student&session=...``, carried by the QR
code, renders the public check-in page and never builds the navigation: pages
declared through ``st.navigation`` appear in the sidebar of every visitor, so an
administration page must not be declared at all when a student is looking.
Everything else goes through authentication.
"""

from __future__ import annotations

import pathlib
import sys

# Streamlit Cloud installs from requirements.txt and does not `pip install .`,
# so the src/ layout is made importable here. Locally, `pip install -e .` makes
# this a no-op.
_SRC = pathlib.Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from esa_attendance.ui import login  # noqa: E402
from esa_attendance.ui.pages import (  # noqa: E402
    admin_roster,
    admin_year,
    assiduity,
    student_checkin,
    teacher_dashboard,
)

st.set_page_config(
    page_title="ESA Attendance",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Route the request to the public page or to the authenticated pages."""
    params = st.query_params

    if params.get("mode") == "student":
        student_checkin.render(params.get("session"))
        return

    user = login.require_role()
    login.render_user_box()

    # url_path is explicit on every page: Streamlit otherwise infers it from the
    # callable name, and all five pages expose a function called render().
    pages = [
        st.Page(
            teacher_dashboard.render,
            title="Appel",
            icon="🎓",
            url_path="appel",
            default=True,
        ),
        st.Page(assiduity.render, title="Assiduité", icon="📉", url_path="assiduite"),
    ]
    if user.is_admin:
        pages += [
            st.Page(
                admin_roster.render, title="Référentiel", icon="🗂️", url_path="referentiel"
            ),
            st.Page(
                admin_year.render, title="Année universitaire", icon="📅", url_path="annee"
            ),
        ]

    st.navigation(pages).run()


if __name__ == "__main__":
    main()
