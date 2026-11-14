"""Authorized single-session read-only projection; no raw bindings or proof material."""
import json
import sqlite3
from pathlib import Path

path = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/nexus-home/nexus.db')
connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.5)
connection.row_factory = sqlite3.Row
connection.execute('PRAGMA query_only=ON')
connection.execute('PRAGMA busy_timeout=500')
query = '''SELECT s.lifecycle_state,s.lease_state,s.owner_generation,
 s.stream_epoch IS NOT NULL AS session_stream_present,
 s.local_retirement_json IS NOT NULL AS retirement_present,
 CASE WHEN json_valid(s.local_retirement_json) THEN json_extract(s.local_retirement_json,'$.version') END AS retirement_version,
 CASE WHEN json_valid(s.local_retirement_json) THEN json_extract(s.local_retirement_json,'$.release_kind') END AS retirement_release_kind,
 s.local_retirement_revision,e.generation AS executor_connection_generation,
 r.generation AS recovery_generation,r.state AS recovery_state,r.error_code AS recovery_error,
 p.binding_json IS NOT NULL AS publication_binding_present,
 l.stream_epoch IS NOT NULL AS local_stream_present
 FROM execution_sessions s
 JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id AND o.operation_id=s.open_operation_id
 JOIN execution_executors e ON e.server_id=s.server_id AND e.executor_id=s.executor_id
 LEFT JOIN execution_agent_recovery r ON r.server_id=s.server_id AND r.executor_id=s.executor_id AND r.agent_id=o.subject_agent_id
 LEFT JOIN execution_local_publications p ON p.server_id=s.server_id AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id
 LEFT JOIN execution_local_streams l ON l.server_id=s.server_id AND l.executor_id=s.executor_id AND l.session_id=s.session_id
 WHERE s.session_id=? LIMIT 2'''
try:
    rows = [dict(row) for row in connection.execute(query, ('ses_abdc7fd9ab15ccadc06fe7aec6b9f247',))]
    print(json.dumps({'mode': 'ro/query_only', 'session_id': 'ses_abdc7fd9ab15ccadc06fe7aec6b9f247', 'rows': rows}, indent=2))
finally:
    connection.close()
