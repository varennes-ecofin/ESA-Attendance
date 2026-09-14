-- =============================================================================
-- ESA Attendance -- Migration 001 (revised)
-- Academic-year tagging, maintenance cleanup, aggregation views, RPC helpers.
--
-- This script is NON-BREAKING: the application in production keeps working
-- exactly as before once it has run. The RLS tightening, which does break the
-- current student check-in, lives in 002_rls_lockdown.sql and must be run only
-- once the ported application is deployed.
--
-- Run 000_preflight.sql first. Idempotent: safe to re-run. It deletes no
-- pedagogical data -- purging a past year is a separate, explicit call to
-- purge_academic_year().
--
-- Delete .github/workflows/keep_alive.yml BEFORE running this, otherwise the
-- workflow re-inserts the maintenance rows that section 4 removes.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Academic year helper (French calendar: a year starts on September 1st)
-- -----------------------------------------------------------------------------
-- STABLE (not IMMUTABLE) because timezone conversion depends on the TZ database.
CREATE OR REPLACE FUNCTION public.academic_year_of(ts timestamptz)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = 'public'
AS $$
    SELECT CASE
        WHEN EXTRACT(MONTH FROM (ts AT TIME ZONE 'Europe/Paris')) >= 9
            THEN EXTRACT(YEAR FROM (ts AT TIME ZONE 'Europe/Paris'))::int::text
                 || '-' ||
                 (EXTRACT(YEAR FROM (ts AT TIME ZONE 'Europe/Paris'))::int + 1)::text
        ELSE (EXTRACT(YEAR FROM (ts AT TIME ZONE 'Europe/Paris'))::int - 1)::text
                 || '-' ||
                 EXTRACT(YEAR FROM (ts AT TIME ZONE 'Europe/Paris'))::int::text
    END;
$$;

-- -----------------------------------------------------------------------------
-- 2. Add the academic_year column to both tables
-- -----------------------------------------------------------------------------
ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS academic_year text;
ALTER TABLE attendance_records  ADD COLUMN IF NOT EXISTS academic_year text;

-- Backfill existing rows from their timestamps / parent session.
UPDATE attendance_sessions
   SET academic_year = academic_year_of(started_at)
 WHERE academic_year IS NULL;

UPDATE attendance_records r
   SET academic_year = COALESCE(s.academic_year, academic_year_of(r.checked_in_at))
  FROM attendance_sessions s
 WHERE r.session_id = s.session_id
   AND r.academic_year IS NULL;

-- Orphan records (parent session already gone) fall back to their own timestamp.
UPDATE attendance_records
   SET academic_year = academic_year_of(checked_in_at)
 WHERE academic_year IS NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_academic_year
    ON attendance_sessions(academic_year);
CREATE INDEX IF NOT EXISTS idx_records_academic_year
    ON attendance_records(academic_year);

-- -----------------------------------------------------------------------------
-- 3. Triggers: never insert a row without an academic year again
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_session_academic_year()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = 'public'
AS $$
BEGIN
    IF NEW.academic_year IS NULL THEN
        NEW.academic_year := academic_year_of(COALESCE(NEW.started_at, now()));
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.set_record_academic_year()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = 'public'
AS $$
BEGIN
    IF NEW.academic_year IS NULL THEN
        SELECT s.academic_year
          INTO NEW.academic_year
          FROM attendance_sessions s
         WHERE s.session_id = NEW.session_id;

        NEW.academic_year := COALESCE(
            NEW.academic_year,
            academic_year_of(COALESCE(NEW.checked_in_at, now()))
        );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sessions_academic_year ON attendance_sessions;
CREATE TRIGGER trg_sessions_academic_year
    BEFORE INSERT ON attendance_sessions
    FOR EACH ROW EXECUTE FUNCTION set_session_academic_year();

DROP TRIGGER IF EXISTS trg_records_academic_year ON attendance_records;
CREATE TRIGGER trg_records_academic_year
    BEFORE INSERT ON attendance_records
    FOR EACH ROW EXECUTE FUNCTION set_record_academic_year();

-- -----------------------------------------------------------------------------
-- 4. Remove the keep-alive machinery (obsolete on the paid plan)
-- -----------------------------------------------------------------------------
DELETE FROM attendance_records
 WHERE session_id LIKE 'PING\_%'
    OR session_id IN (
        SELECT session_id FROM attendance_sessions
         WHERE course_code = 'ESA_MAINTENANCE'
    );

DELETE FROM attendance_sessions
 WHERE session_id LIKE 'PING\_%'
    OR course_code = 'ESA_MAINTENANCE';

-- Close ghost sessions left open by a browser crash or a forgotten tab.
UPDATE attendance_sessions
   SET status = 'closed',
       ended_at = COALESCE(ended_at, started_at)
 WHERE status = 'active'
   AND started_at < now() - interval '1 day';

-- Now that every row is tagged, make the column mandatory.
ALTER TABLE attendance_sessions ALTER COLUMN academic_year SET NOT NULL;
ALTER TABLE attendance_records  ALTER COLUMN academic_year SET NOT NULL;

-- -----------------------------------------------------------------------------
-- 5. Server-side check-in
--
-- Creating this function changes nothing for the running application: it only
-- becomes the single entry point once 002 removes the permissive policies.
-- SECURITY DEFINER lets it validate the session and reject duplicates without
-- the client ever reading attendance_records -- which is what makes dropping
-- the public SELECT policy possible.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.check_in(
    p_session_id   text,
    p_student_id   text,
    p_student_name text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
    v_status   text;
    v_year     text;
    v_inserted int;
BEGIN
    SELECT status, academic_year
      INTO v_status, v_year
      FROM attendance_sessions
     WHERE session_id = p_session_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'unknown_session');
    END IF;

    IF v_status <> 'active' THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'session_closed');
    END IF;

    IF coalesce(btrim(p_student_id), '') = ''
       OR coalesce(btrim(p_student_name), '') = '' THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'invalid_student');
    END IF;

    INSERT INTO attendance_records
        (session_id, student_id, student_name, academic_year, checked_in_at)
    VALUES
        (p_session_id, p_student_id, p_student_name, v_year, now())
    ON CONFLICT (session_id, student_id) DO NOTHING;

    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    IF v_inserted = 0 THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'already_checked_in');
    END IF;

    RETURN jsonb_build_object('ok', true, 'academic_year', v_year);
END;
$$;

REVOKE ALL ON FUNCTION public.check_in(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.check_in(text, text, text) TO anon, service_role;

-- -----------------------------------------------------------------------------
-- 6. Aggregation views (replace the N+1 REST loops in the dashboard)
--
-- security_invoker = true keeps RLS enforced for the calling role, so these
-- views are readable only by service_role.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS session_statistics;

CREATE OR REPLACE VIEW public.course_attendance_stats
WITH (security_invoker = true) AS
SELECT s.academic_year,
       s.course_code,
       count(DISTINCT s.session_id)                      AS num_sessions,
       count(r.id)                                       AS total_checkins,
       round(count(r.id)::numeric
             / NULLIF(count(DISTINCT s.session_id), 0), 2) AS avg_per_session
  FROM attendance_sessions s
  LEFT JOIN attendance_records r ON r.session_id = s.session_id
 WHERE s.status = 'closed'
 GROUP BY s.academic_year, s.course_code;

-- One flat view for the assiduity panel: a single request replaces the
-- chunked .in_() fetching that worked around the REST URL length limit.
CREATE OR REPLACE VIEW public.attendance_detail
WITH (security_invoker = true) AS
SELECT s.academic_year,
       s.session_id,
       s.course_code,
       s.started_at,
       r.student_id,
       r.student_name,
       r.checked_in_at
  FROM attendance_sessions s
  LEFT JOIN attendance_records r ON r.session_id = s.session_id
 WHERE s.status = 'closed';

-- -----------------------------------------------------------------------------
-- 7. Purge of an archived year (called from the admin page, after CSV export)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.purge_academic_year(p_year text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
    v_records  int;
    v_sessions int;
BEGIN
    IF p_year IS NULL OR p_year !~ '^\d{4}-\d{4}$' THEN
        RAISE EXCEPTION 'Invalid academic year format: %', p_year;
    END IF;

    DELETE FROM attendance_records WHERE academic_year = p_year;
    GET DIAGNOSTICS v_records = ROW_COUNT;

    DELETE FROM attendance_sessions WHERE academic_year = p_year;
    GET DIAGNOSTICS v_sessions = ROW_COUNT;

    RETURN jsonb_build_object(
        'academic_year',    p_year,
        'deleted_records',  v_records,
        'deleted_sessions', v_sessions
    );
END;
$$;

REVOKE ALL ON FUNCTION public.purge_academic_year(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.purge_academic_year(text) TO service_role;

COMMIT;

-- =============================================================================
-- Verification queries (run separately, after COMMIT)
-- =============================================================================
-- SELECT academic_year, count(*) AS sessions FROM attendance_sessions
--  GROUP BY 1 ORDER BY 1;
-- SELECT academic_year, count(*) AS records  FROM attendance_records
--  GROUP BY 1 ORDER BY 1;
-- SELECT * FROM course_attendance_stats ORDER BY academic_year, course_code;

-- =============================================================================
-- SMOKE TEST -- run separately; creates then removes one throwaway session
-- =============================================================================
-- INSERT INTO attendance_sessions (session_id, course_code, teacher_username, status)
-- VALUES ('TEST_MIGRATION', 'ESA1PR03', 'migration_test', 'active');
--
-- -- academic_year must have been filled by the trigger:
-- SELECT session_id, academic_year, status FROM attendance_sessions
--  WHERE session_id = 'TEST_MIGRATION';
--
-- SELECT public.check_in('TEST_MIGRATION', 'test_001', 'Etudiant Test');
--   -- expected: {"ok": true, "academic_year": "..."}
-- SELECT public.check_in('TEST_MIGRATION', 'test_001', 'Etudiant Test');
--   -- expected: {"ok": false, "reason": "already_checked_in"}
-- SELECT public.check_in('NO_SUCH_SESSION', 'test_001', 'Etudiant Test');
--   -- expected: {"ok": false, "reason": "unknown_session"}
--
-- SELECT student_id, academic_year FROM attendance_records
--  WHERE session_id = 'TEST_MIGRATION';
--
-- DELETE FROM attendance_records  WHERE session_id = 'TEST_MIGRATION';
-- DELETE FROM attendance_sessions WHERE session_id = 'TEST_MIGRATION';
