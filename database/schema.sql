-- ========================================
-- ESA ATTENDANCE SYSTEM - SUPABASE SCHEMA
-- VERSION FINALE ET SÉCURISÉE
-- ========================================

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
-- Activer RLS sur les tables (tout refuser par défaut)
ALTER TABLE attendance_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY;

-- ========================================
-- 4. RLS POLICIES (SECTION SÉCURISÉE)
-- ========================================
-- Ces politiques concernent l'utilisateur 'anon' (étudiant)
-- L'utilisateur 'service_role' (enseignant) ignore RLS.

-- POLITIQUE 1:
-- L'étudiant (anon) doit pouvoir LIRE les sessions pour que
-- le code Python "is_session_active" puisse fonctionner.
CREATE POLICY "RLS: Public CAN READ sessions"
    ON attendance_sessions
    FOR SELECT
    USING (true);

-- POLITIQUE 2:
-- L'étudiant (anon) doit pouvoir LIRE les enregistrements pour que
-- le code Python de "vérification des doublons" puisse fonctionner.
CREATE POLICY "RLS: Public CAN SELECT records"
    ON attendance_records
    FOR SELECT
    USING (true);

-- POLITIQUE 3 (LA POLITIQUE DE SÉCURITÉ PRINCIPALE):
-- L'étudiant (anon) ne peut INSÉRER que si le 'session_id'
-- de la nouvelle ligne est PRÉSENT dans la liste des sessions "actives".
CREATE POLICY "RLS: Public CAN INSERT records for ACTIVE sessions"
    ON attendance_records
    FOR INSERT
    WITH CHECK (
        session_id IN (
            SELECT s.session_id
            FROM public.attendance_sessions s
            WHERE s.status = 'active'
        )
    );

-- ========================================
-- 5. FUNCTIONS & TRIGGERS
-- ========================================

-- Fonction pour mettre à jour le timestamp 'updated_at'
-- Inclut le correctif de sécurité 'search_path'
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = 'public'; -- Correctif de sécurité

-- Trigger pour appeler la fonction ci-dessus
DROP TRIGGER IF EXISTS update_attendance_sessions_updated_at ON attendance_sessions;
CREATE TRIGGER update_attendance_sessions_updated_at
    BEFORE UPDATE ON attendance_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ========================================
-- 6. REALTIME SUBSCRIPTIONS
-- ========================================
-- Activer realtime pour les deux tables
ALTER PUBLICATION supabase_realtime ADD TABLE attendance_sessions;
ALTER PUBLICATION supabase_realtime ADD TABLE attendance_records;

-- ========================================
-- 7. HELPFUL VIEWS (OPTIONAL)
-- ========================================

-- Vue pour obtenir les statistiques de session
CREATE OR REPLACE VIEW session_statistics AS
SELECT 
    s.session_id,
    s.course_code,
    s.teacher_username,
    s.status,
    s.started_at,
    s.ended
