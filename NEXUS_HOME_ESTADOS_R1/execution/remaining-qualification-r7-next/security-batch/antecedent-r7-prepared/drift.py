"""Public column-level drift report; private cells never leave own Temp."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def classify(root, before, after):
    private = root / 'control/security-private'
    left = json.loads((private / (before + '.json')).read_text())
    right = json.loads((private / (after + '.json')).read_text())
    assert left.keys() == right.keys()
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
            'causality':'NOT_ATTRIBUTED', 'ignored_tables':[], 'ignored_columns':[],
            'private_rows_curated':False}
