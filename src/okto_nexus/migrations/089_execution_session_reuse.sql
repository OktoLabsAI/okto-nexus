-- Preserve start selection and one durable confirmation per reuse intent.
ALTER TABLE execution_client_intents ADD COLUMN session_selection TEXT NOT NULL
    DEFAULT 'explicit' CHECK (session_selection IN ('explicit','automatic','reuse'));
ALTER TABLE execution_client_intents ADD COLUMN reuse_admitted_at TEXT;
