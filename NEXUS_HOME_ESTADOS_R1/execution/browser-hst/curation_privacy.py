"""Redact own fixture CAS values; keep raw evidence private and hash-addressed."""
import hashlib
import json


def cas_values(root):
    path=root/'control/question-preflight.json';values=set()
    if not path.exists():return values
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='cas_token'and isinstance(item,str):values.add(item)
                else:walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(json.loads(path.read_text(encoding='utf-8')))
    return values


def redact(raw,values):
    count=0
    for value in values:
        encoded=value.encode('utf-8');count+=raw.count(encoded)
        raw=raw.replace(encoded,b'<redacted-fixture-cas>')
    return raw,count


def fingerprints(values):
    return sorted(hashlib.sha256(value.encode()).hexdigest()for value in values)
