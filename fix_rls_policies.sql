-- Fix RLS Policies for Sifra.ai Backend (Service Role / Anon Key compatibility)

-- 1. Observation Learnings Table
-- Allow all authenticated/anon roles to SELECT, INSERT, UPDATE so the backend can read patterns and insert new learnings.
CREATE POLICY "Allow anon select on observation_learnings" ON observation_learnings FOR SELECT USING (true);
CREATE POLICY "Allow anon insert on observation_learnings" ON observation_learnings FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon update on observation_learnings" ON observation_learnings FOR UPDATE USING (true);

-- 2. Conversations Table
-- Allow backend to read and write conversations for context and history.
CREATE POLICY "Allow anon select on conversations" ON conversations FOR SELECT USING (true);
CREATE POLICY "Allow anon insert on conversations" ON conversations FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon update on conversations" ON conversations FOR UPDATE USING (true);

-- 3. Observation Log Table (Optional, just in case)
-- Allow backend to log new raw observations
CREATE POLICY "Allow anon select on observation_log" ON observation_log FOR SELECT USING (true);
CREATE POLICY "Allow anon insert on observation_log" ON observation_log FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon update on observation_log" ON observation_log FOR UPDATE USING (true);

-- NOTE: If the tables don't have RLS enabled yet, you can enable them with:
-- ALTER TABLE observation_learnings ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE observation_log ENABLE ROW LEVEL SECURITY;
