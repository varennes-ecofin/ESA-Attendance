"""
Authentication module for ESA Attendance Application
Provides secure login functionality for teachers
"""

import streamlit as st
import hashlib
import hmac
from typing import Tuple, Optional


def hash_password(password: str, salt: str = "esa_attendance_salt") -> str:
    """
    Hash a password using SHA-256 with a salt.
    
    Args:
        password: Plain text password
        salt: Salt string for additional security
        
    Returns:
        Hashed password as hex string
    """
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(stored_hash: str, password: str, salt: str = "esa_attendance_salt") -> bool:
    """
    Verify a password against a stored hash.
    
    Args:
        stored_hash: Previously hashed password
        password: Plain text password to verify
        salt: Salt string used for hashing
        
    Returns:
        True if password matches, False otherwise
    """
    return hmac.compare_digest(stored_hash, hash_password(password, salt))


def check_authentication() -> Tuple[bool, Optional[str]]:
    """
    Check if user is authenticated via session state.
    
    Returns:
        Tuple of (is_authenticated, username)
    """
    if "authenticated" in st.session_state and st.session_state["authenticated"]:
        return True, st.session_state.get("username", None)
    return False, None


def login_form() -> bool:
    """
    Display login form and handle authentication.
    
    Returns:
        True if authentication successful, False otherwise
    """
    st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1>🎓 ESA Attendance System</h1>
        <h3>Teacher Login</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Create centered columns for the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            st.markdown("### 🔐 Authentication Required")
            st.markdown("Please enter your credentials to access the attendance system.")
            
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            
            submit_button = st.form_submit_button("Login", use_container_width=True)
            
            if submit_button:
                if authenticate_user(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = username
                    st.success(f"✅ Welcome {username}!")
                    st.rerun()
                    return True
                else:
                    st.error("❌ Invalid username or password")
                    return False
        
        # Help section
        with st.expander("ℹ️ Need help?"):
            st.markdown("""
            **First time using the system?**
            
            Contact the master administrator to get your credentials:
            - Email: master.esa@univ-orleans.fr
            
            **Security Notice:**
            - Never share your credentials
            - Use a strong password
            - Log out after each session
            """)
    
    return False


def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate a user against stored credentials.
    
    Args:
        username: Username to authenticate
        password: Password to verify
        
    Returns:
        True if authentication successful, False otherwise
    """
    try:
        # Get credentials from Streamlit secrets
        if "teachers" not in st.secrets:
            st.error("⚠️ Authentication system not configured properly. Contact administrator.")
            return False
        
        teachers = st.secrets["teachers"]
        
        # Check if username exists
        if username not in teachers:
            return False
        
        # Get stored password hash
        stored_hash = teachers[username]
        
        # Verify password
        return verify_password(stored_hash, password)
        
    except Exception as e:
        st.error(f"⚠️ Authentication error: {str(e)}")
        return False


def logout():
    """
    Log out the current user and clear session state.
    """
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    st.rerun()


def require_authentication():
    """
    Decorator-like function to require authentication before accessing a page.
    Place this at the top of your main app code.
    
    Returns:
        True if authenticated, False if login form is displayed
    """
    is_authenticated, username = check_authentication()
    
    if not is_authenticated:
        login_form()
        st.stop()  # Stop execution until user is authenticated
        return False
    
    return True


def display_user_info():
    """
    Display current user information and logout button in sidebar.
    """
    is_authenticated, username = check_authentication()
    
    if is_authenticated:
        with st.sidebar:
            st.markdown("---")
            st.markdown(f"**👤 Logged in as:** {username}")
            if st.button("🚪 Logout", use_container_width=True):
                logout()


def generate_password_hash(password: str) -> str:
    """
    Helper function to generate password hash for configuration.
    Use this to create hashes for the secrets.toml file.
    
    Args:
        password: Plain text password
        
    Returns:
        Password hash to store in secrets
    """
    return hash_password(password)


# Utility function for initial setup
def print_password_hash(username: str, password: str):
    """
    Print password hash for adding to secrets.toml.
    Run this function separately to generate hashes for new teachers.
    
    Args:
        username: Teacher username
        password: Teacher password
    """
    hashed = generate_password_hash(password)
    print("\nAdd this to your .streamlit/secrets.toml:\n")
    print('[teachers]')
    print(f'{username} = "{hashed}"\n')


if __name__ == "__main__":
    # Example: Generate password hashes for configuration
    print("=== ESA Attendance - Password Hash Generator ===\n")
    
    # Example teachers
    teachers = [
        ("prof.dupont", "SecurePass123!"),
        ("prof.martin", "AnotherSecure456!"),
        ("admin", "AdminPassword789!")
    ]
    
    print("Copy these lines to your .streamlit/secrets.toml file:\n")
    print("[teachers]")
    for username, password in teachers:
        hashed = generate_password_hash(password)
        print(f'{username} = "{hashed}"')
    
    print("\n⚠️ Remember to change these default passwords!")
