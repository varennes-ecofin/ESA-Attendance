"""
Email sending utilities for attendance notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import streamlit as st

def send_attendance_email(recipient: str, course_name: str, date: str, students: list) -> bool:
    """
    Send attendance list by email
    
    Args:
        recipient: Email address of the recipient
        course_name: Name of the course
        date: Date of the session
        students: List of dictionaries with student info {'name': str, 'time': str}
        
    Returns:
        Success status
    """
    try:
        # Get email configuration from secrets
        sender_email = st.secrets["email"]["sender"]
        sender_password = st.secrets["email"]["password"]
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = st.secrets["email"]["smtp_port"]
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = f"Attendance List - {course_name} - {date}"
        message["From"] = sender_email
        message["To"] = recipient
        
        # Create HTML content
        html_content = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; }}
                    table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                    th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                    th {{ background-color: #4CAF50; color: white; }}
                    tr:nth-child(even) {{ background-color: #f2f2f2; }}
                    .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>📋 Attendance Report</h1>
                </div>
                <div class="content">
                    <h2>{course_name}</h2>
                    <p><strong>Date:</strong> {date}</p>
                    <p><strong>Total Present:</strong> {len(students)} students</p>
                    
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Student Name</th>
                                <th>Check-in Time</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        # Add student rows
        for idx, student in enumerate(students, 1):
            check_time = datetime.fromisoformat(student['time']).strftime('%H:%M:%S')
            html_content += f"""
                            <tr>
                                <td>{idx}</td>
                                <td>{student['name']}</td>
                                <td>{check_time}</td>
                            </tr>
            """
        
        html_content += """
                        </tbody>
                    </table>
                    
                    <div class="footer">
                        <p>This email was generated automatically by the ESA Attendance System.</p>
                        <p>Master ESA - Econométrie et Statistique Appliquée</p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        # Attach HTML content
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient, message.as_string())
        
        return True
        
    except Exception as e:
        st.error(f"Error sending email: {e}")
        return False
