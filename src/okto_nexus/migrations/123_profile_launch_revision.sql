-- Server policy revisions must not rewrite executor-owned launch consent.
-- Canonical realizations are prepared with launch profile revision 1.
ALTER TABLE runtime_profiles ADD COLUMN launch_revision INTEGER NOT NULL DEFAULT 1 CHECK (launch_revision > 0);
UPDATE runtime_profiles SET launch_revision = revision
WHERE NOT EXISTS (SELECT 1 FROM agent_endpoints ep
                  WHERE ep.profile_id = runtime_profiles.profile_id AND ep.protocol = 'nxl-r4');
