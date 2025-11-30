"""
Supabase Database Module for ESA Attendance System
Handles all database operations including real-time updates
"""

import streamlit as st
from supabase import create_client, Client
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import pandas as pd


class AttendanceDatabase:
    """
    Database handler for attendance system using Supabase.
    Manages sessions, attendance records, and real-time updates.
    """
    
    def __init__(self, supabase_client: Client):
        """Initialize with a pre-configured Supabase client."""
        self.supabase = supabase_client
    
    def keep_alive(self) -> bool:
        """
        Effectue une requête légère pour maintenir la base active.
        Ne modifie pas les données réelles.
        """
        try:
            # On demande juste le nombre de sessions, c'est une requête API valide
            self.supabase.table("attendance_sessions").select("session_id", count="exact").limit(1).execute()
            return True
        except Exception as e:
            st.error(f"Erreur de ping: {e}")
            return False
        
        
    # ========================================
    # SESSION MANAGEMENT
    # ========================================
    
    def create_session(self, session_id: str, course_code: str, 
                    teacher_username: str) -> bool:
        """
        Create a new attendance session.
        """
        try:
            data = {
                "session_id": session_id,
                "course_code": course_code,
                "teacher_username": teacher_username,
                "status": "active",
                "started_at": datetime.now().isoformat(),
                "ended_at": None
            }
            
            _result = self.supabase.table("attendance_sessions").insert(data).execute()
            return True
            
        except Exception as e:
            st.error(f"Error creating session: {e}")
            return False
    
    
    def close_session(self, session_id: str) -> bool:
        """
        Close an active attendance session.
        """
        try:
            _result = self.supabase.table("attendance_sessions").update({
                "status": "closed",
                "ended_at": datetime.now().isoformat()
            }).eq("session_id", session_id).execute()
            
            return True
            
        except Exception as e:
            st.error(f"Error closing session: {e}")
            return False
    
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session details.
        """
        try:
            result = self.supabase.table("attendance_sessions")\
                .select("*")\
                .eq("session_id", session_id)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            st.error(f"Error fetching session: {e}")
            return None
    
    
    def is_session_active(self, session_id: str) -> bool:
        """
        Check if a session is currently active.
        """
        session = self.get_session(session_id)
        return session and session.get("status") == "active"
    
    
    # ========================================
    # ATTENDANCE RECORDS
    # ========================================
    
    def record_attendance(self, session_id: str, student_id: str, 
                        student_name: str) -> Tuple[bool, str]:
        """
        Record a student's attendance.
        """
        try:
            # Check if session is active
            if not self.is_session_active(session_id):
                return False, "Session is not active"
            
            # Check if already recorded
            existing = self.supabase.table("attendance_records")\
                .select("*")\
                .eq("session_id", session_id)\
                .eq("student_id", student_id)\
                .execute()
            
            if existing.data:
                return False, "Already checked in"
            
            # Record attendance
            data = {
                "session_id": session_id,
                "student_id": student_id,
                "student_name": student_name,
                "checked_in_at": datetime.now().isoformat()
            }
            
            _result = self.supabase.table("attendance_records").insert(data).execute()
            return True, "Attendance recorded successfully"
            
        except Exception as e:
            return False, f"Error recording attendance: {e}"
    
    
    def get_session_attendance(self, session_id: str) -> List[Dict]:
        """
        Get all attendance records for a session.
        """
        try:
            result = self.supabase.table("attendance_records")\
                .select("*")\
                .eq("session_id", session_id)\
                .order("checked_in_at", desc=False)\
                .execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            st.error(f"Error fetching attendance: {e}")
            return []
    
    
    def get_attendance_count(self, session_id: str) -> int:
        """
        Get the count of students who checked in.
        """
        attendance = self.get_session_attendance(session_id)
        return len(attendance)
    
    
    def get_attendance_dataframe(self, session_id: str) -> pd.DataFrame:
        """
        Get attendance records as a pandas DataFrame for display.
        """
        attendance = self.get_session_attendance(session_id)
        
        if not attendance:
            return pd.DataFrame(columns=["Student Name", "Check-in Time"])
        
        data = []
        for record in attendance:
            # Parse ISO timestamp and format it
            timestamp = datetime.fromisoformat(record['checked_in_at'].replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%H:%M:%S")
            
            data.append({
                "Student Name": record['student_name'],
                "Check-in Time": formatted_time
            })
        
        return pd.DataFrame(data)
    
    
    # ========================================
    # STATISTICS & REPORTS
    # ========================================
    
    def get_teacher_sessions(self, teacher_username: str, 
                            limit: int = 10) -> List[Dict]:
        """
        Get recent sessions for a teacher.
        """
        try:
            result = self.supabase.table("attendance_sessions")\
                .select("*")\
                .eq("teacher_username", teacher_username)\
                .order("started_at", desc=True)\
                .limit(limit)\
                .execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            st.error(f"Error fetching teacher sessions: {e}")
            return []
    
    
    def get_course_statistics(self, course_code: str) -> Dict:
        """
        Get statistics for a course across all sessions.
        """
        try:
            # Get all sessions for this course
            sessions = self.supabase.table("attendance_sessions")\
                .select("session_id")\
                .eq("course_code", course_code)\
                .execute()
            
            if not sessions.data:
                return {
                    "total_sessions": 0,
                    "total_attendance": 0,
                    "average_attendance": 0
                }
            
            session_ids = [s['session_id'] for s in sessions.data]
            
            # Get attendance for all sessions
            total_attendance = 0
            for session_id in session_ids:
                count = self.get_attendance_count(session_id)
                total_attendance += count
            
            return {
                "total_sessions": len(session_ids),
                "total_attendance": total_attendance,
                "average_attendance": total_attendance / len(session_ids) if session_ids else 0
            }
            
        except Exception as e:
            st.error(f"Error calculating statistics: {e}")
            return {}
    
    
    # ========================================
    # EXPORT FUNCTIONS
    # ========================================
    
    def export_session_to_csv(self, session_id: str) -> Optional[str]:
        """
        Export session attendance to CSV format.
        """
        try:
            df = self.get_attendance_dataframe(session_id)
            
            if df.empty:
                return None
            
            return df.to_csv(index=False)
            
        except Exception as e:
            st.error(f"Error exporting to CSV: {e}")
            return None
    
    
    def get_session_summary(self, session_id: str) -> Dict:
        """
        Get a complete summary of a session for email/export.
        """
        try:
            session = self.get_session(session_id)
            attendance = self.get_session_attendance(session_id)
            
            if not session:
                return {}
            
            return {
                "session_id": session_id,
                "course_code": session.get("course_code"),
                "teacher": session.get("teacher_username"),
                "started_at": session.get("started_at"),
                "ended_at": session.get("ended_at"),
                "status": session.get("status"),
                "total_present": len(attendance),
                "students": [
                    {
                        "name": record['student_name'],
                        "time": record['checked_in_at']
                    }
                    for record in attendance
                ]
            }
            
        except Exception as e:
            st.error(f"Error generating summary: {e}")
            return {}


# ========================================
# SINGLETON INSTANCES
# ========================================
# (Modifié pour gérer deux types de clients : anon et service)

def _get_supabase_client(role: str = 'anon') -> Client:
    """Crée un client Supabase basé sur le rôle."""
    url = st.secrets["supabase"]["url"]
    
    if role == 'service':
        key = st.secrets["supabase"]["service_key"]
    else:
        key = st.secrets["supabase"]["key"]
        
    if not url or not key:
        raise ValueError(f"Supabase URL or Key not found for role '{role}'")
        
    return create_client(url, key)

@st.cache_resource
def get_service_db() -> AttendanceDatabase:
    """
    Get or create a singleton database instance for SERVICE ROLE (admin).
    """
    return AttendanceDatabase(_get_supabase_client('service'))

@st.cache_resource
def get_anon_db() -> AttendanceDatabase:
    """
    Get or create a singleton database instance for ANON ROLE (public).
    """
    return AttendanceDatabase(_get_supabase_client('anon'))
