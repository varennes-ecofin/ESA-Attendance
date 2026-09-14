-- =============================================================================
-- ESA Attendance -- 000: pre-flight inspection (READ ONLY)
--
-- Run this first, block by block, and keep the output. Nothing is modified.
-- Its purpose is to check that the assumptions behind migration 001 hold on
-- the live database, in particular the exact names of the existing RLS
-- policies: `DROP POLICY IF EXISTS` on a wrong name fails silently and would
-- leave a permissive policy in place.
-- =============================================================================

-- 1. Which tables and columns exist -------------------------------------------
SELECT table_name, column_name, data_type, is_nullable
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name IN ('attendance_sessions', 'attendance_records')
 ORDER BY table_name, ordinal_position;

-- 2. Volume, and how much of it is keep-alive noise ---------------------------
SELECT 'sessions total'        AS item, count(*) AS n FROM attendance_sessions
UNION ALL
SELECT 'sessions maintenance', count(*) FROM attendance_sessions
 WHERE course_code = 'ESA_MAINTENANCE' OR session_id LIKE 'PING\_%'
UNION ALL
SELECT 'sessions still active', count(*) FROM attendance_sessions
 WHERE status = 'active'
UNION ALL
SELECT 'records total',        count(*) FROM attendance_records;

-- 3. Time span, i.e. how many academic years are actually in there ------------
SELECT min(started_at) AS first_session,
       max(started_at) AS last_session
  FROM attendance_sessions;

-- 4. Existing RLS policies -- COMPARE THESE NAMES WITH SCRIPT 002 -------------
SELECT tablename, policyname, cmd, roles, qual, with_check
  FROM pg_policies
 WHERE schemaname = 'public'
   AND tablename IN ('attendance_sessions', 'attendance_records')
 ORDER BY tablename, policyname;

-- 5. Is RLS actually enabled on both tables -----------------------------------
SELECT relname, relrowsecurity AS rls_enabled, relforcerowsecurity AS rls_forced
  FROM pg_class
 WHERE relname IN ('attendance_sessions', 'attendance_records');

-- 6. Existing views, functions and triggers that migration 001 will touch -----
SELECT table_name AS view_name
  FROM information_schema.views
 WHERE table_schema = 'public';

SELECT routine_name
  FROM information_schema.routines
 WHERE routine_schema = 'public'
 ORDER BY routine_name;

SELECT tgname AS trigger_name, relname AS on_table
  FROM pg_trigger t
  JOIN pg_class c ON c.oid = t.tgrelid
 WHERE NOT t.tgisinternal
   AND relname IN ('attendance_sessions', 'attendance_records');
