"""
ESA Attendance App - Main Application with Supabase Integration
Attendance Management System for Master ESA
Real-time updates using Supabase database

Launch in terminal: streamlit run app.py
"""

import streamlit as st
import qrcode
from io import BytesIO
# import pandas as pd
from datetime import datetime
import time

# Import authentication module
import esa_auth

# Import database module
# from utils.database import get_database
from utils.database import get_service_db, get_anon_db

# Import your existing functions
try:
    from utils.courses import get_courses, get_students
    from utils.email_sender import send_attendance_email
except ImportError:
    st.error("⚠️ Cannot import required modules. Check your imports.")


# Page configuration
st.set_page_config(
    page_title="ESA Attendance System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)


def get_url_params():
    """
    Get URL parameters to determine if this is student or teacher mode.
    
    Returns:
        dict with 'mode' and 'session' keys
    """
    query_params = st.query_params
    return {
        'mode': query_params.get('mode', 'teacher'),  # Default to teacher mode
        'session': query_params.get('session', None)
    }


def student_checkin_page(session_id):
    """
    Public page for students to check in (no authentication required).
    Uses Supabase for real-time persistence.
    
    Args:
        session_id: Active attendance session ID
    """
    
    # Display ESA logo (small)
    logo_url = "https://raw.githubusercontent.com/varennes-ecofin/ESA-Attendance/main/data/ESALogoNewWebLightBG-02.png"
    st.markdown(f"""
    <div style='text-align: center; padding: 0.5rem 0;'>
        <img src='{logo_url}' style='max-width: 300px; width: 100%; height: auto;'>
    </div>
    """, unsafe_allow_html=True)
    
    st.title("🎓 ESA Attendance - Student Check-in")   
    
    # Get database instance
    # db = get_database()
    db = get_anon_db()
    
    if not session_id:
        st.error("❌ Invalid session. Please scan the QR code again.")
        st.stop()
        return
    
    # Check if session exists and is active
    if not db.is_session_active(session_id):
        st.error("❌ This session is not active or does not exist.")
        st.info("Please ask your teacher to start a new session.")
        st.stop()
        return
    
    # Get session details
    session = db.get_session(session_id)
    course_code = session.get('course_code')
    
    # Get course information
    courses = get_courses()
    if course_code not in courses:
        st.error(f"❌ Course {course_code} not found.")
        st.stop()
        return
    
    # Display course information
    st.info(f"📚 **Course:** {courses[course_code]}")
    
    # Get students for this course
    students = get_students(course_code)
    
    if not students:
        st.error("❌ No students found for this course.")
        st.stop()
        return
    
    # Session state for tracking check-in status
    if 'checked_in' not in st.session_state:
        st.session_state.checked_in = False
    if 'selected_student' not in st.session_state:
        st.session_state.selected_student = None
    
    # If already checked in, show confirmation
    if st.session_state.checked_in:
        st.success("✅ **Check-in confirmed!**")
        # st.balloons()
        
        student_name = st.session_state.selected_student
        check_in_time = datetime.now().strftime("%H:%M:%S")
        
        st.markdown(f"""
        ### Your attendance has been recorded:
        - **Name:** {student_name}
        - **Course:** {courses[course_code]}
        - **Time:** {check_in_time}
        
        You can close this window now.
        """)
        
        # if st.button("🔄 Check in another student"):
        #     st.session_state.checked_in = False
        #     st.session_state.selected_student = None
        #     st.rerun()
        
        st.stop()
        return
    
    # Student selection interface
    st.markdown("### 👤 Select your name")
    st.markdown("Please find and select your name from the list below:")
    
    # Add search functionality
    search_term = st.text_input("🔍 Search your name:", placeholder="Type to search...")
    
    # Filter students based on search
    if search_term:
        filtered_students = [s for s in students if search_term.lower() in s['name'].lower()]
    else:
        filtered_students = students
    
    if not filtered_students:
        st.warning("No students found matching your search. Please try again.")
        st.stop()
        return
    
    # Display as radio buttons for better mobile UX
    selected_name = st.radio(
        "Select your name:",
        options=[s['name'] for s in filtered_students],
        key="student_selector"
    )
    
    # Find selected student
    selected_student = next((s for s in students if s['name'] == selected_name), None)
    
    if selected_student:
        st.markdown("---")
        st.markdown(f"**You selected:** {selected_student['name']}")
        
        # Confirmation section
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("✅ Confirm Attendance", type="primary", key="confirm_btn"):
                # Record attendance in Supabase
                success, message = db.record_attendance(
                    session_id=session_id,
                    student_id=selected_student['id'],
                    student_name=selected_student['name']
                )
                
                if success:
                    # Mark as checked in
                    st.session_state.checked_in = True
                    st.session_state.selected_student = selected_student['name']
                    st.rerun()
                else:
                    st.error(f"❌ {message}")
        
        with col2:
            if st.button("❌ Cancel"):
                st.rerun()
    
    # Display session info at bottom
    with st.expander("ℹ️ Session Information"):
        st.write(f"**Session ID:** {session_id}")
        st.write(f"**Course Code:** {course_code}")
        st.write(f"**Number of students:** {len(students)}")


def teacher_dashboard():
    """
    Authenticated dashboard for teachers (authentication required).
    Uses Supabase for real-time updates.
    """
    # ========================================
    # AUTHENTICATION CHECK
    # ========================================
    if not esa_auth.require_authentication():
        return  # Stop if not authenticated
    
    # Display user info and logout button
    esa_auth.display_user_info()
    
    # Get database instance
    # db = get_database()
    db = get_service_db()
    
    # ========================================
    # TEACHER DASHBOARD
    # ========================================
    
    # Display ESA logo (small)
    logo_url = "https://raw.githubusercontent.com/varennes-ecofin/ESA-Attendance/main/data/ESALogoNewWebLightBG-02.png"
    st.markdown(f"""
    <div style='text-align: center; padding: 0.5rem 0;'>
        <img src='{logo_url}' style='max-width: 300px; width: 100%; height: auto;'>
    </div>
    """, unsafe_allow_html=True) 
    
    st.title("🎓 ESA Attendance System - Teacher Dashboard")
    
    
    # Get authenticated username
    _, username = esa_auth.check_authentication()
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Session Configuration")
        
        # ========================================
        # COURSE SELECTION
        # ========================================
        st.subheader("1️⃣ Select Course")
        
        courses = get_courses()
        
        selected_course = st.selectbox(
            "Choose your course:",
            options=list(courses.keys()),
            format_func=lambda x: courses[x]
        )
        
        st.markdown("---")
        st.subheader("📋 Session Controls")
        
        # Display recent sessions
        with st.expander("📚 Recent Sessions"):
            recent_sessions = db.get_teacher_sessions(username, limit=5)
            if recent_sessions:
                for sess in recent_sessions:
                    status_emoji = "🟢" if sess['status'] == 'active' else "⚪"
                    st.write(f"{status_emoji} {sess['course_code']} - {sess['started_at'][:10]}")
            else:
                st.info("No recent sessions")
                
        st.markdown("---")
        st.subheader("🔧 Maintenance")
        if st.button("📡 Ping Base de Données", help="Cliquez ici une fois par semaine pour empêcher Supabase de mettre la base en pause."):
            if db.keep_alive():
                st.toast("✅ Base de données pingée avec succès !", icon="🚀")
            else:
                st.toast("❌ Échec du ping.", icon="⚠️")
    
    # Main content area
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📱 QR Code for Students")
        
        # Session state initialization
        if 'session_active' not in st.session_state:
            st.session_state.session_active = False
            st.session_state.session_id = None
        
        # Start/Stop session buttons
        if not st.session_state.session_active:
            if st.button("🟢 Start Attendance Session", key='start_session'):
                # Create new session
                session_id = f"{selected_course}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                # Save to database
                if db.create_session(session_id, selected_course, username):
                    st.session_state.session_id = session_id
                    st.session_state.session_active = True
                    st.session_state.current_course = selected_course
                    st.success("✅ Session created in database!")
                    st.rerun()
                else:
                    st.error("❌ Failed to create session")
        else:
            if st.button("🔴 Close Session", key='close_session'):
                # Close session in database
                if db.close_session(st.session_state.session_id):
                    st.session_state.session_active = False
                    st.success("✅ Session closed!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Failed to close session")
        
        # Generate and display QR code if session is active
        if st.session_state.session_active:
            st.success("✅ Session Active")
            
            # Generate QR code URL
            base_url = st.secrets.get("base_url", "https://esa-attendance.streamlit.app")
            # base_url = st.secrets.get("base_url", "http://localhost:8501")
            qr_url = f"{base_url}?session={st.session_state.session_id}&mode=student"
            
            # Create QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr_image = qr.make_image(fill_color="black", back_color="white")
            
            # Display QR code
            buf = BytesIO()
            qr_image.save(buf, format="PNG")
            st.image(buf.getvalue())
            
            st.caption("Students scan this QR code to check in")
            
            # Manual test link
            st.markdown("---")
            st.markdown("**🧪 Test Links**")
            st.markdown(f"[📱 Open Student View]({qr_url})")
            st.caption("Click to test student interface")
            
            # Display session info
            with st.expander("ℹ️ Session Details"):
                session_data = db.get_session(st.session_state.session_id)
                if session_data:
                    st.write(f"**Session ID:** {session_data['session_id']}")
                    st.write(f"**Course:** {session_data['course_code']}")
                    st.write(f"**Status:** {session_data['status']}")
                    st.write(f"**Started:** {session_data['started_at']}")
        else:
            st.info("👆 Click 'Start Attendance Session' to begin")
    
    with col2:
        st.subheader("✅ Live Attendance")
        
        if st.session_state.session_active:
            # Get real-time attendance from database
            df = db.get_attendance_dataframe(st.session_state.session_id)
            
            if not df.empty:
                # Display attendance list
                st.dataframe(
                    df,
                    hide_index=True
                )
                
                # Progress bar
                students = get_students(selected_course)
                total_students = len(students) if students else 50
                
                progress = len(df) / total_students
                st.progress(progress)
                st.caption(f"✅ {len(df)} / {total_students} students checked in ({progress:.0%})")
                
                # Action buttons
                st.markdown("---")
                col_send, col_export, col_refresh = st.columns([2, 2, 1])
                
                with col_send:
                    if st.button("📧 Send Email", key='send_email'):
                        recipient = st.secrets.get("email", {}).get("recipient_email", "")
                        
                        if not recipient:
                            st.warning("⚠️ No recipient email configured in secrets.toml")
                        else:
                            # Prepare data for email
                            course_name = courses.get(selected_course, selected_course)
                            session_date = datetime.now().strftime("%Y-%m-%d")
                            
                            # Get attendance with ISO timestamps (not formatted DataFrame)
                            attendance_records = db.get_session_attendance(st.session_state.session_id)
                            students_list = []
                            for record in attendance_records:
                                students_list.append({
                                    'name': record['student_name'],
                                    'time': record['checked_in_at']  # ✅ Format ISO complet
                                })
                            
                            # Send email
                            with st.spinner("Sending email..."):
                                success = send_attendance_email(
                                    recipient=recipient,
                                    course_name=course_name,
                                    date=session_date,
                                    students=students_list
                                )
                            
                            if success:
                                st.success(f"✅ Email sent successfully to {recipient}!")
                            else:
                                st.error("❌ Failed to send email. Check your email configuration.")
                
                with col_export:
                    csv = db.export_session_to_csv(st.session_state.session_id)
                    if csv:
                        st.download_button(
                            label="💾 Download CSV",
                            data=csv,
                            file_name=f"attendance_{st.session_state.session_id}.csv",
                            mime="text/csv",
                            key='download_csv'
                        )
                
                with col_refresh:
                    if st.button("🔄", key='refresh_btn'):
                        st.rerun()
            else:
                st.info("⏳ Waiting for students to check in...")
                st.caption("The list will update automatically")
            
            # Auto-refresh every 5 seconds
            time.sleep(5)
            st.rerun()
        else:
            st.info("Start a session to see live attendance")
            
            # Show statistics
            st.markdown("---")
            st.subheader("📊 Overall Statistics")
            stats = db.get_course_statistics(selected_course)
            if stats.get('total_sessions', 0) > 0:
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Total Sessions", stats['total_sessions'])
                col_b.metric("Total Attendance", stats['total_attendance'])
                col_c.metric("Avg per Session", f"{stats['average_attendance']:.1f}")
            else:
                st.info("No sessions yet for this course")
                
            # Display statistics table for all courses
            st.markdown("---")
            st.subheader("📊 Courses Statistics")
            
            # Get statistics for all courses
            all_stats = get_all_courses_statistics(db)
            
            if all_stats:
                # Create DataFrame for better display
                import pandas as pd
                df_stats = pd.DataFrame(all_stats)
                
                # Sort by year and course code
                df_stats = df_stats.sort_values(['year', 'course_code'])
                
                # Format for display
                df_display = pd.DataFrame({
                    'Course Code': df_stats['course_code'],
                    'Course Name': df_stats['course_name'],
                    'Year': df_stats['year'],
                    'Sessions': df_stats['num_sessions'],
                    'Avg Participation Rate': df_stats['participation_rate'].apply(lambda x: f"{x:.1f}%")
                })
                
                # Display table
                st.dataframe(
                    df_display,
                    hide_index=True,
                    width='stretch'
                )
                
                st.caption(f"📈 Showing statistics for {len(all_stats)} courses with attendance data")
            else:
                st.info("No courses with attendance data yet")

@st.cache_data(ttl=3600)
def get_all_courses_statistics(_db):
    """
    Get statistics for all courses with attendance data.
    (Mise en cache pour 1 heure (3600s) pour éviter les recalculs constants)
    
    Args:
        db: Database instance
        
    Returns:
        List of dictionaries containing course statistics
    """
    from utils.courses import COURSES, get_students
    
    stats_list = []
    
    for course_code, course_info in COURSES.items():
        # Get all sessions for this course
        try:
            sessions = _db.supabase.table("attendance_sessions")\
                .select("session_id")\
                .eq("course_code", course_code)\
                .execute()
            
            num_sessions = len(sessions.data) if sessions.data else 0
            
            if num_sessions == 0:
                # Skip courses without sessions
                continue
            
            # Get total attendance across all sessions
            total_attendance = 0
            session_ids = [s['session_id'] for s in sessions.data]
            
            for session_id in session_ids:
                attendance = _db.supabase.table("attendance_records")\
                    .select("id", count="exact")\
                    .eq("session_id", session_id)\
                    .execute()
                total_attendance += len(attendance.data) if attendance.data else 0
            
            # Calculate average participation rate
            students = get_students(course_code)
            num_students = len(students) if students else 0
            
            if num_students > 0 and num_sessions > 0:
                # Average attendance per session
                avg_attendance_per_session = total_attendance / num_sessions
                # Participation rate as percentage
                participation_rate = (avg_attendance_per_session / num_students) * 100
            else:
                participation_rate = 0
            
            stats_list.append({
                'course_code': course_code,
                'course_name': course_info['name'],
                'year': course_info['year'],
                'num_sessions': num_sessions,
                'participation_rate': participation_rate
            })
            
        except Exception:
            # Skip courses with errors
            continue
    
    return stats_list


def main():
    """
    Main application entry point with authentication.
    """
    # Get URL parameters to determine mode
    params = get_url_params()
    mode = params['mode']
    session_id = params['session']
    
    # Route based on mode
    if mode == 'student':
        # Public student check-in page (no authentication)
        student_checkin_page(session_id)
    else:
        # Teacher dashboard (requires authentication)
        teacher_dashboard()


# Entry point
if __name__ == "__main__":
    main()
