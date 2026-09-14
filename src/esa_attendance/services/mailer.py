"""Attendance report e-mail.

Kept free of Streamlit so failures surface as exceptions the caller can render
however it likes, instead of the previous ``st.error`` buried in the sender.
"""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Sequence

from ..config import EmailSettings


class MailError(RuntimeError):
    """Raised when the attendance report cannot be sent."""


def _format_time(iso_timestamp: str) -> str:
    """Return a local ``HH:MM:SS`` rendering of an ISO timestamp."""
    try:
        moment = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return iso_timestamp
    return moment.astimezone().strftime("%H:%M:%S")


def _build_html(course_label: str, session_date: str, records: Sequence[dict]) -> str:
    """Render the HTML body of the report.

    Args:
        course_label: Course name shown in the heading.
        session_date: Date of the session, already formatted.
        records: Rows with ``student_name`` and ``checked_in_at`` keys.

    Returns:
        The HTML document.
    """
    rows = "".join(
        f"<tr><td>{index}</td><td>{escape(str(record['student_name']))}</td>"
        f"<td>{_format_time(str(record['checked_in_at']))}</td></tr>"
        for index, record in enumerate(records, start=1)
    )
    return f"""<html><head><style>
      body {{ font-family: Arial, Helvetica, sans-serif; color: #222; }}
      .header {{ background:#2b6a4d; color:#fff; padding:18px; text-align:center; }}
      table {{ border-collapse: collapse; width:100%; margin-top:18px; }}
      th, td {{ border:1px solid #ddd; padding:10px; text-align:left; }}
      th {{ background:#2b6a4d; color:#fff; }}
      tr:nth-child(even) {{ background:#f4f4f4; }}
      .footer {{ margin-top:28px; font-size:12px; color:#666; }}
    </style></head><body>
      <div class="header"><h2>Feuille de présence</h2></div>
      <div style="padding:18px">
        <h3>{escape(course_label)}</h3>
        <p><strong>Date :</strong> {escape(session_date)}<br>
           <strong>Présents :</strong> {len(records)}</p>
        <table><thead><tr><th>#</th><th>Étudiant</th><th>Heure</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <div class="footer">
          <p>Message généré automatiquement par ESA Attendance.</p>
          <p>Master ESA — Économétrie et Statistique Appliquée</p>
        </div>
      </div>
    </body></html>"""


def send_attendance_report(
    settings: EmailSettings,
    course_label: str,
    session_date: str,
    records: Sequence[dict],
    recipients: Sequence[str] | None = None,
) -> list[str]:
    """Send the attendance report by e-mail.

    Args:
        settings: SMTP configuration.
        course_label: Course name shown in the message.
        session_date: Date of the session.
        records: Attendance rows, each with ``student_name`` and
            ``checked_in_at``.
        recipients: Override for the configured recipients.

    Returns:
        The list of addresses the message was sent to.

    Raises:
        MailError: If no recipient is configured or the SMTP exchange fails.
    """
    targets = list(recipients or settings.recipients)
    if not targets:
        raise MailError(
            "Aucun destinataire configuré (email.recipient_email dans les secrets)."
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Présences — {course_label} — {session_date}"
    message["From"] = settings.sender
    message["To"] = ", ".join(targets)
    message.attach(MIMEText(_build_html(course_label, session_date, records), "html"))

    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(settings.sender, settings.password)
            server.sendmail(settings.sender, targets, message.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Envoi impossible : {exc}") from exc

    return targets
