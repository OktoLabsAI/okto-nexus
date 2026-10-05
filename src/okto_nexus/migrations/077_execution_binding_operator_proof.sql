-- A proof authorizes only the immutable proposal diff; it is not a runtime grant.
ALTER TABLE execution_proposals ADD COLUMN operator_proof_json TEXT;
