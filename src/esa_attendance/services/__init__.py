"""Domain services: assiduity analytics and outbound e-mail."""

from .analytics import AssiduityResult, compute_assiduity
from .mailer import MailError, send_attendance_report

__all__ = [
    "AssiduityResult",
    "compute_assiduity",
    "MailError",
    "send_attendance_report",
]