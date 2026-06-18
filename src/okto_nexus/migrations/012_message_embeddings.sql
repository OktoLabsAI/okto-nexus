-- Okto Nexus migration 012: per-message embedding vectors (Frente 3).
-- Forward-only. Stores ONE embedding per message for semantic (cosine) search.
-- The embedding's lifecycle is coupled to the message via ON DELETE CASCADE
-- (decision D-EMB-5): deleting a message - by reset OR by the messages reaper -
-- drops its embedding automatically, so no orphan vector can ever survive.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- vec: the embedding serialised as little-endian float32 (dim * 4 bytes).
-- model/dim: provenance + shape guard (search ignores rows whose dim != query).
CREATE TABLE IF NOT EXISTS message_embeddings (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id) ON DELETE CASCADE,
    vec BLOB NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- Cosine search scans every row (brute force over a small set: only NEW
-- messages are embedded). The dim index lets the shape guard skip incompatible
-- rows cheaply after a provider/model change.
CREATE INDEX IF NOT EXISTS idx_message_embeddings_dim ON message_embeddings (dim);
