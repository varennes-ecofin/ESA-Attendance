-- ========================================
-- ESA ATTENDANCE SYSTEM - SUPABASE SCHEMA
-- ========================================
-- Execute this SQL in your Supabase SQL Editor to create the required tables

-- ========================================
-- 1. ATTENDANCE SESSIONS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    course_code TEXT NOT NULL,
    teacher_username TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON attendance_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_teacher ON attendance_sessions(teacher_username);
CREATE INDEX IF NOT EXISTS idx_sessions_course ON attendance_sessions(course_code);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON attendance_sessions(status);

-- ========================================
-- 2. ATTENDANCE RECORDS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS attendance_records (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    student_name TEXT NOT NULL,
    checked_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Prevent duplicate check-ins
    UNIQUE(session_id, student_id)
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_records_session ON attendance_records(session_id);
CREATE INDEX IF NOT EXISTS idx_records_student ON attendance_records(student_id);
CREATE INDEX IF NOT EXISTS idx_records_time ON attendance_records(checked_in_at);

-- ========================================
-- 3. ENABLE ROW LEVEL SECURITY (RLS)
-- ========================================
-- Enable RLS on tables
ALTER TABLE attendance_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY;

-- ========================================
-- 4. RLS POLICIES
-- ========================================

-- Policy for attendance_sessions: Allow all authenticated users to read
CREATE POLICY "Allow public read access to sessions"
    ON attendance_sessions
    FOR SELECT
    USING (true);

-- Policy for attendance_sessions: Allow authenticated users to insert
CREATE POLICY "Allow authenticated users to create sessions"
    ON attendance_sessions
    FOR INSERT
    WITH CHECK (true);

-- Policy for attendance_sessions: Allow users to update their own sessions
CREATE POLICY "Allow users to update their own sessions"
    ON attendance_sessions
    FOR UPDATE
    USING (true);

-- Policy for attendance_records: Allow public read access
CREATE POLICY "Allow public read access to records"
    ON attendance_records
    FOR SELECT
    USING (true);

-- Policy for attendance_records: Allow anyone to insert records
CREATE POLICY "Allow anyone to insert attendance records"
    ON attendance_records
    FOR INSERT
    WITH CHECK (true);

-- ========================================
-- 5. FUNCTIONS & TRIGGERS
-- ========================================

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
DROP TRIGGER IF EXISTS update_attendance_sessions_updated_at ON attendance_sessions;
CREATE TRIGGER update_attendance_sessions_updated_at
    BEFORE UPDATE ON attendance_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ========================================
-- 6. REALTIME SUBSCRIPTIONS
-- ========================================
-- Enable realtime for both tables
ALTER PUBLICATION supabase_realtime ADD TABLE attendance_sessions;
ALTER PUBLICATION supabase_realtime ADD TABLE attendance_records;

-- ========================================
-- 7. HELPFUL VIEWS (OPTIONAL)
-- ========================================

-- View to get session statistics
CREATE OR REPLACE VIEW session_statistics AS
SELECT 
    s.session_id,
    s.course_code,
    s.teacher_username,
    s.status,
    s.started_at,
    s.ended_at,
    COUNT(r.id) AS total_attendees,
    ARRAY_AGG(r.student_name ORDER BY r.checked_in_at) AS student_names
FROM 
    attendance_sessions s
LEFT JOIN 
    attendance_records r ON s.session_id = r.session_id
GROUP BY 
    s.session_id, s.course_code, s.teacher_username, s.status, s.started_at, s.ended_at;

-- ========================================
-- 8. SAMPLE DATA (OPTIONAL - FOR TESTING)
-- ========================================
/*
-- Insert a test session
INSERT INTO attendance_sessions (session_id, course_code, teacher_username, status)
VALUES ('TEST_20250101_120000', 'ESA1AN01', 'test_teacher', 'active');

-- Insert test attendance records
INSERT INTO attendance_records (session_id, student_id, student_name)
VALUES 
    ('TEST_20250101_120000', 'm1_001', 'Test Student 1'),
    ('TEST_20250101_120000', 'm1_002', 'Test Student 2');
*/

-- ========================================
-- VERIFICATION QUERIES
-- ========================================
-- Run these to verify everything is set up correctly

-- Check tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('attendance_sessions', 'attendance_records');

-- Check RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE tablename IN ('attendance_sessions', 'attendance_records');

-- Check policies exist
SELECT schemaname, tablename, policyname 
FROM pg_policies 
WHERE tablename IN ('attendance_sessions', 'attendance_records');

-- ========================================
-- NOTES
-- ========================================
/*
IMPORTANT NOTES:

1. ROW LEVEL SECURITY:
   - Currently set to allow public access for ease of use
   - For production, you should restrict policies based on authentication
   - Example: Only allow teachers to create/update their own sessions

2. REALTIME:
   - Realtime is enabled for both tables
   - The app will receive updates when new attendance is recorded
   - Make sure Realtime is enabled in your Supabase project settings

3. INDEXES:
   - Indexes are created for common query patterns
   - This improves performance for filtering by session_id, teacher, etc.

4. UNIQUE CONSTRAINT:
   - The (session_id, student_id) combination is unique
   - This prevents duplicate check-ins for the same student in a session

5. TIMESTAMPS:
   - All times are stored in TIMESTAMPTZ (timezone-aware)
   - Automatically converted to local time by the application

6. CLEANUP:
   - Consider adding a scheduled job to archive old sessions
   - Example: Move sessions older than 1 year to an archive table
*/