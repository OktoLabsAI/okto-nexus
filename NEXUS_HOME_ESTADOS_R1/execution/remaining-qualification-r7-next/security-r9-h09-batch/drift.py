"""Public column-level drift report; private cells never leave own Temp."""
import hashlib
import json
from datetime import datetime


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def allow_exact_observations(root, old, new, sequences):
    """Accept only exact known publisher inserts, never updates/deletes/types."""
    expected_columns = {'event_id','workspace_id','stream','type','actor_agent_id',
                        'payload','visibility','target','created_at'}
    assert set(old['columns']) == set(new['columns']) == expected_columns
    columns = new['columns']
    id_index = columns.index('event_id')
    previous_ids = {row[id_index] for row in old['rows']}
    candidates = [row for row in new['rows'] if row[id_index] not in previous_ids]
    accepted, errors, removed_ids = [], [], set()
    def stamp(value):
        result = datetime.fromisoformat(value.replace('Z','+00:00'))
        assert result.tzinfo is not None
        return result
    for sequence in sequences:
        expected = json.loads((root/'control/security-private'/('expected-observation-'+str(sequence)+'.json')).read_text())
        payload = expected['payload']
        assert payload['observational_only'] is True and type(payload['sequence']) is int
        assert payload['sequence'] == sequence
        assert expected['type'] == ('observation.activity' if sequence == 1 else 'observation.completion')
        assert expected['visibility'] == 'private' and expected['stream'] == 'workspace'
        def matches(row):
            item = dict(zip(columns,row,strict=True))
            try:
                observed = json.loads(item['payload'])
                target = json.loads(item['target'])
                return (type(item['event_id']) is int and item['event_id']>max(previous_ids,default=0)
                    and all(item[key] == expected[key] for key in (
                        'workspace_id','stream','type','actor_agent_id','visibility'))
                    and digest(observed) == digest(payload) and observed['observational_only'] is True
                    and type(observed['sequence']) is int and type(observed['generation']) is int
                    and target == expected['target']
                    and stamp(expected['created_at_bounds'][0]) <= stamp(item['created_at']) <= stamp(expected['created_at_bounds'][1]))
            except (ValueError, TypeError, KeyError, AssertionError):
                return False
        found = [row for row in candidates if matches(row)]
        if len(found) != 1 or found[0][id_index] in removed_ids:
            errors.append({'sequence':sequence,'reason':'Exact expected observation event missing or nonunique'})
            continue
        row = found[0]
        removed_ids.add(row[id_index])
        accepted.append({'type':expected['type'],'source_id':payload['source_id'],
            'observed_instance_id':payload['observed_instance_id'],'generation':payload['generation'],
            'sequence':sequence,'private_event_sha256':digest(row),
            'receipt_report_hash':payload['report_hash'],'observational_only':True})
    # Original captured rows remain untouched on disk. No preexisting row,
    # table/column/type is ignored; all extra inserts remain ordinary drift.
    new['rows'] = [row for row in new['rows'] if row[id_index] not in removed_ids]
    return accepted, errors


def classify(root, before, after, *, allow_observations=False):
    private = root / 'control/security-private'
    left = json.loads((private / (before + '.json')).read_text())
    right = json.loads((private / (after + '.json')).read_text())
    assert left.keys() == right.keys()
    allowed, expected_errors = [], []
    if allow_observations:
        assert before == 'before-obs' and after in {'after-idle','after-completion'}
        allowed, expected_errors = allow_exact_observations(root,left['events'],right['events'],
            (1,) if after == 'after-idle' else (1,2))
    changes = []
    for table, old in left.items():
        new = right[table]
        assert old['columns'] == new['columns'] and old['primary_key'] == new['primary_key']
        if old['rows'] == new['rows']:
            continue
        columns = old['columns']
        keys = old['primary_key']
        if not keys:
            changed = [name for index, name in enumerate(columns) if sorted(
                digest(row[index]) for row in old['rows']) != sorted(digest(row[index]) for row in new['rows'])]
            changes.append({'table':table, 'before_rows':len(old['rows']), 'after_rows':len(new['rows']),
                            'classification':'rowset_changed_without_primary_key',
                            'changed_column_multisets':changed,
                            'column_causality':'No row identity; cell transitions not inferred',
                            'before_sha256':digest(old['rows']), 'after_sha256':digest(new['rows'])})
            continue
        def keyed(rows):
            result = {}
            for row in rows:
                key = digest([row[columns.index(name)] for name in keys])
                assert key not in result
                result[key] = row
            return result
        a, b = keyed(old['rows']), keyed(new['rows'])
        changed_columns = {}
        for key in a.keys() & b.keys():
            for index, name in enumerate(columns):
                if a[key][index] != b[key][index]:
                    changed_columns[name] = changed_columns.get(name, 0) + 1
        changes.append({'table':table, 'added_rows':len(b.keys()-a.keys()),
                        'removed_rows':len(a.keys()-b.keys()), 'changed_columns':changed_columns})
    return {'before':before, 'after':after, 'changes':changes,
            'allowed_observation_events':allowed,'expected_observation_errors':expected_errors,
            'causality':'NOT_ATTRIBUTED', 'ignored_tables':[], 'ignored_columns':[],
            'private_rows_curated':False}
