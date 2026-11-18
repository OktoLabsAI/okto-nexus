-- A saved open is bound to one retired source for its entire lifetime.
ALTER TABLE execution_sessions ADD COLUMN saved_resume_json TEXT
    CHECK (saved_resume_json IS NULL OR (json_valid(saved_resume_json)
        AND json_extract(saved_resume_json, '$.source_session_id') IS NOT NULL
        AND json_extract(saved_resume_json, '$.source_session_generation') IS NOT NULL
        AND json_extract(saved_resume_json, '$.source_close_operation_id') IS NOT NULL
        AND json_extract(saved_resume_json, '$.source_release_digest') IS NOT NULL));

CREATE UNIQUE INDEX execution_sessions_saved_resume_origin
    ON execution_sessions(server_id, executor_id,
        json_extract(saved_resume_json, '$.source_session_id'),
        json_extract(saved_resume_json, '$.source_session_generation'))
    WHERE saved_resume_json IS NOT NULL;
