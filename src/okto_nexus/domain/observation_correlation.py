"""Pure, versioned evidence for an explicitly selected OBS/native correlation.

The host supplies authenticated canonical records and a separately acquired OS
identity. This module performs no discovery, authentication or liveness check.
Its proof describes that comparison at the host's recorded verification instant;
it never establishes present process ownership or execution authority. External
binding selection remains an operator attestation, even when native birth agrees.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import re


MAX_INT64 = (1 << 63) - 1
MAX_PID = (1 << 32) - 1
PROOF_KIND = "local_windows_process_v1"
EXTERNAL_PROVENANCE = "operator_attested_external_binding"
NATIVE_PROVENANCE = "machine_checked_native_birth"
_INVALID = "OBSERVATION_CORRELATION_INVALID"
_MISMATCH = "OBSERVATION_CORRELATION_PROOF_MISMATCH"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BIRTH = re.compile(r"filetime:[0-9a-f]{16}\Z")
_OBS_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
_SELECTION_IDS = (
    "source_id", "observed_instance_id", "server_id", "executor_id", "session_id",
    "open_operation_id", "stream_epoch", "binding_id", "workspace_binding_id",
)
_SELECTION_REVISIONS = (
    "source_revision", "generation", "session_owner_generation", "expected_correlation_revision",
)
_EVIDENCE_FIELDS = frozenset({
    "kind", "host_id", "pid", "creation_filetime", "image_path", "binding_hash",
})
_OS_FIELDS = frozenset({"host_id", "pid", "creation_filetime", "image_path"})
_RECORD_FIELDS = frozenset({
    "server_id", "executor_id", "session_id", "opening_operation_id", "platform", "pid", "birth_token",
})
_PROOF_FIELDS = frozenset({
    "kind", "external_binding_provenance", "native_birth_provenance", "host_id", "pid",
    "creation_filetime", "image_path_sha256", "binding_hash",
})


class ObservationCorrelationError(ValueError):
    """Fixed diagnostic only; supplied keys, values and paths never enter errors."""

    def __init__(self, code: str = _INVALID):
        self.code = code if code in (_INVALID, _MISMATCH) else _INVALID
        super().__init__("Observation correlation unavailable: " + self.code)


def _invalid():
    raise ObservationCorrelationError()


def _object(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _invalid()
    return value


def _text(value, maximum=160):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or not value.isprintable() or value.strip() != value):
        _invalid()
    try:
        value.encode("utf-8")
    except UnicodeError:
        _invalid()
    return value


def _integer(value, *, minimum=1, maximum=MAX_INT64):
    if type(value) is not int or not minimum <= value <= maximum:
        _invalid()
    return value


def _matching(value, pattern):
    if type(value) is not str or not pattern.fullmatch(value):
        _invalid()
    return value


def _image(value):
    value = _text(value, 32767)
    # Accept the drive-qualified extended spelling returned by Windows, never
    # a UNC/device/relative target. This is string normalization, not path I/O.
    if value.startswith("\\\\?\\"):
        value = value[4:]
    drive, tail = ntpath.splitdrive(value)
    if (not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith(("\\", "/"))
            or any(char in tail for char in ':*?"<>|')):
        _invalid()
    normalized = ntpath.normcase(ntpath.normpath(value))
    if normalized.endswith("\\") or ntpath.basename(normalized) in ("", ".", ".."):
        _invalid()
    return normalized


def normalize_selection(value: dict) -> dict:
    """Return a detached, closed selection; zero means no prior correlation."""
    _object(value, (*_SELECTION_IDS, *_SELECTION_REVISIONS))
    result = {name: _text(value[name]) for name in _SELECTION_IDS}
    for name in ("source_id", "observed_instance_id"):
        _matching(result[name], _OBS_ID)
    for name in _SELECTION_REVISIONS:
        result[name] = _integer(value[name], minimum=0 if name == "expected_correlation_revision" else 1)
    return result


def _normalize_os_identity(value):
    _object(value, _OS_FIELDS)
    return dict(host_id=_matching(value["host_id"], _HEX),
                pid=_integer(value["pid"], maximum=MAX_PID),
                creation_filetime=_integer(value["creation_filetime"]), image_path=_image(value["image_path"]))


def normalize_evidence(value: dict) -> dict:
    """Validate operator-selected evidence; the normalized path is not a proof."""
    _object(value, _EVIDENCE_FIELDS)
    if type(value["kind"]) is not str or value["kind"] != PROOF_KIND:
        _invalid()
    return dict(kind=PROOF_KIND, **_normalize_os_identity({name: value[name] for name in _OS_FIELDS}),
                binding_hash=_matching(value["binding_hash"], _DIGEST))


def _normalize_record(value):
    _object(value, _RECORD_FIELDS)
    result = {name: _text(value[name]) for name in
              ("server_id", "executor_id", "session_id", "opening_operation_id")}
    if type(value["platform"]) is not str or value["platform"] != "win32":
        _invalid()
    result.update(platform="win32", pid=_integer(value["pid"], maximum=MAX_PID),
                  birth_token=_matching(value["birth_token"], _BIRTH))
    _integer(int(result["birth_token"][9:], 16))
    return result


def verify_native_birth(selection: dict, evidence: dict, *, native_record: dict, os_identity: dict) -> dict:
    """Compare an exact Core namespace/opening and independently read OS birth.

    ``native_record`` is the host's minimal projection of ProcessBirthRecord;
    accepting an arbitrary caller JSON as that record would not verify anything.
    The host also revalidates source, owner/stream fences and operator authority
    before persisting. No process state or continuing liveness is returned here.
    """
    selected = normalize_selection(selection)
    external = normalize_evidence(evidence)
    record = _normalize_record(native_record)
    observed = _normalize_os_identity(os_identity)
    if (any(record[name] != selected[name] for name in ("server_id", "executor_id", "session_id"))
            or record["opening_operation_id"] != selected["open_operation_id"]
            or any(external[name] != observed[name] for name in _OS_FIELDS)
            or record["pid"] != observed["pid"]
            or record["birth_token"] != f'filetime:{observed["creation_filetime"]:016x}'):
        raise ObservationCorrelationError(_MISMATCH)
    return dict(kind=PROOF_KIND, external_binding_provenance=EXTERNAL_PROVENANCE,
                native_birth_provenance=NATIVE_PROVENANCE, host_id=observed["host_id"], pid=observed["pid"],
                creation_filetime=observed["creation_filetime"],
                image_path_sha256="sha256:" + hashlib.sha256(observed["image_path"].encode("utf-8")).hexdigest(),
                binding_hash=external["binding_hash"])


def _normalize_proof(value):
    _object(value, _PROOF_FIELDS)
    for name, expected in (("kind", PROOF_KIND), ("external_binding_provenance", EXTERNAL_PROVENANCE),
                           ("native_birth_provenance", NATIVE_PROVENANCE)):
        if type(value[name]) is not str or value[name] != expected:
            _invalid()
    return dict(kind=PROOF_KIND, external_binding_provenance=EXTERNAL_PROVENANCE,
                native_birth_provenance=NATIVE_PROVENANCE, host_id=_matching(value["host_id"], _HEX),
                pid=_integer(value["pid"], maximum=MAX_PID),
                creation_filetime=_integer(value["creation_filetime"]),
                image_path_sha256=_matching(value["image_path_sha256"], _DIGEST),
                binding_hash=_matching(value["binding_hash"], _DIGEST))


def correlation_digest(selection: dict, proof: dict) -> str:
    """Versioned review digest, not a signature or authority/liveness proof."""
    value = dict(schema_version=1, selection=normalize_selection(selection), proof=_normalize_proof(proof))
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fences_match(expected: dict, current: dict | None) -> bool:
    """Compare every selected fence exactly; absent current state invalidates.

    Malformed state raises a sanitized validation error rather than authorizing
    fallback. Callers must additionally check current authorization/availability.
    No matching by label, namespace prefix, missing epoch or replacement ID.
    """
    expected = normalize_selection(expected)
    return current is not None and expected == normalize_selection(current)
