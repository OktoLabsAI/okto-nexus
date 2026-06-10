-- Okto Nexus migration 007: per-session shared secret (M10 trust).
-- Forward-only. session_open generates and RETURNS a random secret (uuid4)
-- stored in this column; in trust_mode='strict' the sensitive verbs
-- (message_create, handoff_claim/complete/reject, inbox_pull/ack/extend)
-- require a matching session_id + session_secret for the acting agent, and in
-- trust_mode='open' a supplied credential is still validated (a mismatch is
-- never ignored). NULL marks sessions opened before this migration: they
-- carry no usable credential and must be re-opened to act in strict mode.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

ALTER TABLE sessions ADD COLUMN session_secret TEXT;
