ALTER TABLE runtime_policy_defaults
ADD COLUMN session_input_admissions_paused INTEGER NOT NULL DEFAULT 0
CHECK (session_input_admissions_paused IN (0, 1));
