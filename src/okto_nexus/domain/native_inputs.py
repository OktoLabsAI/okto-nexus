"""Bounded, non-secret native input contracts; no I/O or implicit answers."""
import json
import math

USER_INPUT = "item/tool/requestUserInput"
ELICITATION = "mcpServer/elicitation/request"
INPUT_METHODS = {USER_INPUT, ELICITATION}


def _require(condition):
    if not condition:
        raise ValueError("Unsupported or invalid native input")


def validate_request(method, params):
    if method == USER_INPUT:
        questions = params.get("questions")
        _require(params.get("isBlocking") is True and isinstance(questions, list) and 1 <= len(questions) <= 16)
        ids = set()
        for q in questions:
            _require(isinstance(q, dict) and isinstance(q.get("id"), str) and 1 <= len(q["id"]) <= 128)
            _require(q["id"] not in ids and q.get("isSecret", False) is False and type(q.get("isOther", False)) is bool)
            _require(all(isinstance(q.get(key), str) for key in ("header", "question")))
            ids.add(q["id"])
            options = q.get("options")
            if options is not None:
                _require(isinstance(options, list) and len(options) <= 16)
                _require(all(isinstance(o, dict) and isinstance(o.get("label"), str) and isinstance(o.get("description"), str) for o in options))
                _require(len({o["label"] for o in options}) == len(options))
    elif method == ELICITATION:
        _require(params.get("mode") == "form" and isinstance(params.get("serverName"), str))
        schema = params.get("requestedSchema")
        _require(isinstance(schema, dict) and schema.get("type") == "object")
        _require(not (set(schema) - {"type", "properties", "required", "$schema", "additionalProperties"}))
        _require(schema.get("additionalProperties", False) is False)
        props, required = schema.get("properties"), schema.get("required") or []
        _require(isinstance(props, dict) and 1 <= len(props) <= 16 and isinstance(required, list))
        _require(all(isinstance(k, str) and 1 <= len(k) <= 128 for k in props))
        _require(all(isinstance(k, str) and k in props for k in required) and len(set(required)) == len(required))
        for prop in props.values():
            _require(isinstance(prop, dict) and prop.get("type") in ("string", "boolean", "number", "integer"))
            _require(not (set(prop) - {"type", "title", "description", "default", "enum", "minLength", "maxLength", "minimum", "maximum"}))
            if "enum" in prop:
                _require(isinstance(prop["enum"], list) and 1 <= len(prop["enum"]) <= 32)
                for value in prop["enum"]:
                    _value(value, {"type": prop["type"]})
            for name in ("minLength", "maxLength"):
                if prop.get(name) is not None:
                    _require(type(prop[name]) is int and 0 <= prop[name] <= 4096 and prop["type"] == "string")
            for name in ("minimum", "maximum"):
                if prop.get(name) is not None:
                    _require(type(prop[name]) in (int, float) and math.isfinite(prop[name]) and prop["type"] in ("number", "integer"))
    else:
        raise ValueError("Not an input request")


def _value(value, prop):
    kind = prop["type"]
    if kind == "string":
        _require(isinstance(value, str) and len(value) <= 4096)
        _require(prop.get("minLength") is None or len(value) >= prop["minLength"])
        _require(prop.get("maxLength") is None or len(value) <= prop["maxLength"])
    elif kind == "boolean":
        _require(type(value) is bool)
    else:
        _require(type(value) is int if kind == "integer" else type(value) in (int, float))
        _require(math.isfinite(value))
        _require(prop.get("minimum") is None or value >= prop["minimum"])
        _require(prop.get("maximum") is None or value <= prop["maximum"])
    if "enum" in prop:
        _require(value in prop["enum"])


def response_for(request, response, *, approved):
    method, params = request["method"], request["params"]
    if method not in INPUT_METHODS:
        _require(response is None)
        return None
    validate_request(method, params)
    if not approved:
        _require(response is None)
        return {"answers": {}} if method == USER_INPUT else {"action": "decline"}
    _require(isinstance(response, dict))
    _require(len(json.dumps(response, allow_nan=False).encode()) <= 16384)
    if method == USER_INPUT:
        answers = response.get("answers")
        _require(set(response) == {"answers"} and isinstance(answers, dict))
        _require(set(answers) == {q["id"] for q in params["questions"]})
        for q in params["questions"]:
            item = answers[q["id"]]
            _require(isinstance(item, dict) and set(item) == {"answers"})
            values = item["answers"]
            _require(isinstance(values, list) and 1 <= len(values) <= 16)
            _require(all(isinstance(v, str) and 1 <= len(v) <= 4096 for v in values))
            if q.get("options") and not q.get("isOther", False):
                _require(all(v in {o["label"] for o in q["options"]} for v in values))
        return response
    schema, content = params["requestedSchema"], response.get("content")
    _require(set(response) == {"content"} and isinstance(content, dict))
    _require(not (set(content) - set(schema["properties"])) and set(schema.get("required") or []) <= set(content))
    for key, value in content.items():
        _value(value, schema["properties"][key])
    return {"action": "accept", "content": content}
