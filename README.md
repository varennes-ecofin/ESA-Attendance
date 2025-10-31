# 📋 ESA Attendance System

A real-time attendance tracking system built with Streamlit for Master ESA courses but extendable to any formation. Students scan a QR code to check in, and professors see live updates of attendance and send the final report to the administration.

## 🌟 Features

- ✅ **QR Code Generation**: Automatic QR code for easy student access
- 📱 **Mobile-Friendly**: Students check in using their phones
- ⚡ **Real-Time Updates**: Live attendance list updates every 3 seconds
- 📧 **Email Notifications**: Send attendance lists automatically
- 🔒 **Session Management**: Open/close attendance sessions
- 📊 **Progress Tracking**: Visual progress bar for attendance completion

## 🚀 Quick Start (Local Development)

### Prerequisites

- Python 3.8+
- Supabase account (free tier is sufficient)
- Gmail account for sending emails

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/ESA-Attendance.git
cd esa-attendance
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up Supabase database**
   - Go to [supabase.com](https://supabase.com) and create a free account
   - Create a new project
   - Go to SQL Editor and run the contents of `database/schema.sql`
   - Note your project URL and anon key from Settings > API

4. **Configure secrets**
   - Copy `.streamlit/secrets.toml.template` to `.streamlit/secrets.toml`
   - Fill in your credentials:
     ```toml
     base_url = "http://localhost:8501"
     
     [supabase]
     url = "https://your-project.supabase.co"
     key = "your-supabase-anon-key"
     
     [email]
     sender = "your-email@gmail.com"
     password = "your-app-password"
     smtp_server = "smtp.gmail.com"
     smtp_port = 587
     
     recipient_email = "secretary@university.fr"
     ```

5. **Run the app before deployment**
```bash
streamlit run app.py
```

## 🌐 Deployment on Streamlit Cloud

### Step 1: Prepare Your Repository

1. Push your code to GitHub (exclude `.streamlit/secrets.toml`)
2. Make sure `.gitignore` contains:
   ```
   .streamlit/secrets.toml
   __pycache__/
   *.pyc
   .env
   ```

### Step 2: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Connect your GitHub repository
4. Select the repository and set:
   - Main file path: `app.py`
   - Python version: 3.9+

### Step 3: Configure Secrets on Streamlit Cloud

In the Streamlit Cloud dashboard:

1. Go to your app settings
2. Click on "Secrets"
3. Paste your secrets in TOML format:
   ```toml
   base_url = "https://your-app-name.streamlit.app"
   
   [supabase]
   url = "https://your-project.supabase.co"
   key = "your-supabase-anon-key"
   
   [email]
   sender = "your-email@gmail.com"
   password = "your-app-password"
   smtp_server = "smtp.gmail.com"
   smtp_port = 587
   
   recipient_email = "secretary@university.fr"
   ```
4. Save and your app will restart automatically

### Step 4: Update Base URL

After deployment, update the `base_url` in secrets to match your app URL (e.g., `https://ESA-Attendance.streamlit.app`)

## 📧 Gmail Configuration

To send emails from Gmail:

1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password:
   - Go to Google Account > Security
   - Under "2-Step Verification", click "App passwords"
   - Generate a new app password for "Mail"
   - Use this password in your secrets configuration

## 📚 Usage Guide

### For Professors

1. **Start Session**
   - Open the app
   - Select your course from the dropdown
   - Click "Start Attendance Session"

2. **Display QR Code**
   - Show the generated QR code on your projector/screen
   - Students scan it with their phones

3. **Monitor Attendance**
   - Watch the real-time list of students checking in
   - See progress bar fill up

4. **Send Attendance List**
   - Click "Send Attendance List" to email the results
   - The secretary receives a formatted HTML email

5. **Close Session**
   - Click "Close Session" when done
   - This prevents further check-ins

### For Students

1. Scan the QR code with your phone camera
2. Select your name from the dropdown
3. Click "Confirm Attendance"
4. You'll see a confirmation message

## 🛠️ Customization

### Adding Courses

Edit `utils/courses.py` and update the `COURSES` dictionary:

```python
COURSES = {
    "YOURCOURSE": "Course Name",
    # Add more courses
}
```

### Adding Students

Option 1: Edit `utils/courses.py` manually

Option 2: Import from CSV (plan to add this feature in admin panel)

### Changing Email Template

Edit the HTML template in `utils/email_sender.py`

## 📊 Database Schema

### Tables

**sessions**
- `session_id` (VARCHAR): Unique session identifier
- `course_code` (VARCHAR): Course code
- `status` (VARCHAR): 'active' or 'closed'
- `created_at` (TIMESTAMP): Session creation time

**attendances**
- `session_id` (VARCHAR): Links to sessions
- `student_id` (VARCHAR): Student identifier
- `checked_in_at` (TIMESTAMP): Check-in time
- Unique constraint on (session_id, student_id)

## 🔧 Troubleshooting

### QR Code Not Generating
- Check that `qrcode` and `Pillow` are installed
- Verify `base_url` is set correctly in secrets

### Database Connection Issues
- Verify Supabase credentials
- Check that SQL schema has been executed
- Ensure RLS policies are set correctly

### Email Not Sending
- Verify Gmail app password is correct
- Check SMTP settings
- Ensure 2FA is enabled on Google account

### Auto-Refresh Not Working
- This is expected behavior in Streamlit
- The app uses `st.rerun()` with time.sleep(3)
- Each professor session refreshes independently

## 🔒 Security Considerations

- Never commit `secrets.toml` to version control
- Use environment variables or Streamlit secrets
- In production, add authentication for professor view
- Consider adding rate limiting for check-ins
- Review Supabase RLS policies for your use case

## 📝 TODO / Future Enhancements

- [ ] Add admin panel for managing courses/students
- [ ] Statistics dashboard
- [ ] Multiple professor sessions simultaneously
- [ ] Historical attendance reports
- [ ] Mobile app version

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the MIT License.

## 👤 Contact

For questions or support, contact: [master.esa@univ-orleans.fr]

## 🙏 Acknowledgments

- Master ESA for the educational context
- Streamlit for the amazing framework
- Supabase for the database solution
