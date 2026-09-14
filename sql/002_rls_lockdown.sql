-- =============================================================================
-- ESA Attendance -- Migration 002: RLS lockdown
--
-- BREAKING. Run this ONLY when the ported application is deployed, i.e. when
-- the student page calls the check_in() RPC instead of inserting into
-- attendance_records directly. Before that, the old check-in silently fails.
--
-- What it changes:
--   * anon can no longer read attendance_records at all (it used to be able to
--     read every student name and timestamp of every session ever held);
--   * anon can read a session only while it is active;
--   * anon can no longer INSERT directly -- check_in() does it with definer
--     rights, after validating the session and rejecting duplicates.
--
-- service_role, used by the teacher and admin pages, bypasses RLS entirely and
-- is unaffected.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Remove every existing policy on the two tables
--
-- A loop rather than DROP POLICY IF EXISTS on hard-coded names: a policy
-- created from the dashboard, or renamed at some point, would survive a
-- name-based drop without any error, leaving the table readable.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    pol record;
BEGIN
    FOR pol IN
        SELECT tablename, policyname
          FROM pg_policies
         WHERE schemaname = 'public'
           AND tablename IN ('attendance_sessions', 'attendance_records')
    LOOP
        EXECUTE format('DROP POLICY %I ON public.%I', pol.policyname, pol.tablename);
        RAISE NOTICE 'Dropped policy % on %', pol.policyname, pol.tablename;
    END LOOP;
END;
$$;

-- -----------------------------------------------------------------------------
-- 2. Make sure RLS is on (a table with RLS disabled ignores policies entirely)
-- -----------------------------------------------------------------------------
ALTER TABLE attendance_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_records  ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- 3. The single policy a student needs
-- -----------------------------------------------------------------------------
CREATE POLICY "anon reads active sessions only"
    ON attendance_sessions
    FOR SELECT
    TO anon
    USING (status = 'active');

-- No policy at all on attendance_records: every read and write goes through
-- public.check_in(), created in migration 001.

COMMIT;

-- =============================================================================
-- VERIFICATION -- run separately, after COMMIT
-- =============================================================================

-- 1. Exactly one policy should remain, on attendance_sessions.
SELECT tablename, policyname, cmd, roles, qual
  FROM pg_policies
 WHERE schemaname = 'public'
   AND tablename IN ('attendance_sessions', 'attendance_records');

-- 2. Impersonate the anon role and check what it can actually see.
--    A count of 0 on a non-empty table is the expected result: RLS filters
--    rows, it does not raise an error.
--
BEGIN;
  SET LOCAL ROLE anon;
  SELECT count(*) AS records_visible_to_anon FROM attendance_records;
    -- expected: 0
  SELECT status, count(*) FROM attendance_sessions GROUP BY status;
    -- expected: only rows with status = 'active'
  SELECT public.check_in('NO_SUCH_SESSION', 'x', 'y');
    -- expected: {"ok": false, "reason": "unknown_session"}
    -- an error here means the EXECUTE grant from 001 is missing
ROLLBACK;

-- =============================================================================
-- ROLLBACK PLAN -- restores the previous, permissive behaviour
-- =============================================================================
CREATE POLICY "RLS: Public CAN READ sessions"
    ON attendance_sessions FOR SELECT USING (true);
CREATE POLICY "RLS: Public CAN SELECT records"
    ON attendance_records FOR SELECT USING (true);
CREATE POLICY "RLS: Public CAN INSERT records for ACTIVE sessions"
    ON attendance_records FOR INSERT
    WITH CHECK (session_id IN (
        SELECT s.session_id FROM public.attendance_sessions s
         WHERE s.status = 'active'));
