"""Operator-approved local mappings for the canonical R4 realization flow."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import secrets
import time

from nexus_connector_core import CoreError
from nexus_connector_core.discovery import selected_fingerprint
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.execution.core_inventory import resolve_local_installation_selection
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard, _require_binding_method
from .execution_realizations import _persist_realization


def _error(message, code=ErrorCode.CONFLICT):
    return OktoNexusError(code, message, {})


def _digest(value):
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def directory_identity(value):
    try:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError()
        path = path.resolve(strict=True)
        stat = path.stat()
        if not path.is_dir():
            raise ValueError()
        return {"path":str(path), "device":str(stat.st_dev), "inode":str(stat.st_ino)}
    except (OSError, ValueError, TypeError):
        raise _error("The approved local directory is unavailable.") from None


def _validate(request):
    required = {"client_intent_id","agent_id","workspace_root","workspace_id","workspace_label",
                "adapter_id","candidate_ref","inventory_revision","local_consent_id",
                "approved","provider_home","secret_bindings"}
    if type(request) is not dict or set(request) != required or request["approved"] is not True:
        raise _error("Explicit local operator consent is required.", ErrorCode.VALIDATION_ERROR)
    for name in ("client_intent_id","agent_id","adapter_id","candidate_ref","inventory_revision","local_consent_id"):
        if type(request[name]) is not str or not 1 <= len(request[name]) <= 160:
            raise _error("Invalid local realization scope.", ErrorCode.VALIDATION_ERROR)
    if (type(request["workspace_label"]) is not str or len(request["workspace_label"]) > 160
            or any(c in request["workspace_label"] for c in ("/", chr(92), ":"))
            or (request["workspace_id"] is not None and
                (type(request["workspace_id"]) is not str or not 1 <= len(request["workspace_id"]) <= 160))):
        raise _error("Invalid local workspace selection.", ErrorCode.VALIDATION_ERROR)
    for name in ("workspace_root","provider_home"):
        value = request[name]
        if value is None and name == "provider_home":
            continue
        if type(value) is not str or not 1 <= len(value) <= 4096 or "\x00" in value:
            raise _error("Invalid local directory.", ErrorCode.VALIDATION_ERROR)
    bindings = request["secret_bindings"]
    if (type(bindings) is not dict or len(bindings) > 64 or any(
            type(name) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)
            or type(ref) is not str or not 1 <= len(ref) <= 256
            or not ref.startswith(("vault:", "provider:")) or not ref.partition(":")[2].strip()
            or any(c in ref for c in "\r\n\x00")
            or any(prefix in ref for prefix in ("nxs_", "nxsept_", "nxc4_", "nxt4_"))
            for name, ref in bindings.items())):
        raise _error("Only protected secret references may be configured.", ErrorCode.VALIDATION_ERROR)


def _authority(uow, *, owner, access, context, subject, adapter_id):
    if owner is None or not access.authenticate(context, uow=uow):
        raise _error("An authenticated operator must approve local directories.", ErrorCode.PERMISSION_DENIED)
    access.authorize(context, uow=uow, audit=False)
    dispatcher = owner.dispatcher
    if not dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id,
            epoch=dispatcher.epoch, now=access.clock.now_iso()):
        raise _error("The local realization owner is no longer current.")
    current = uow.connection.execute(
        "SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? AND kind='embedded' "
        "AND owner_instance_id=? AND generation=? AND revoked_at IS NULL",
        (owner.key.server_id, owner.key.executor_id, dispatcher.owner_id, owner.generation)).fetchone()
    agent = uow.connection.execute("SELECT 1 FROM agents WHERE agent_id=? AND is_active=1", (subject,)).fetchone()
    if current is None or agent is None:
        raise _error("The local executor or represented agent is unavailable.")
    _require_binding_method(uow.connection, subject_agent_id=subject, adapter_id=adapter_id)
    from .agent_execution_policy import require_execution_location
    require_execution_location(uow, agent_id=subject,
        executor_id=owner.key.executor_id, adapter_id=adapter_id)
    return (_agent_guard(uow.connection, context.actor_agent_id), _agent_guard(uow.connection, subject))


def stage_embedded_realization(factory, *, owner, executor_id, access, context, request):
    """Authorize before filesystem reads; commit private and public evidence atomically."""
    _validate(request)
    if owner is None or executor_id != owner.key.executor_id:
        raise _error("Local configuration requires this Server's embedded executor.", ErrorCode.PERMISSION_DENIED)
    with factory.unit_of_work(write=False) as uow:
        guard = _authority(uow, owner=owner, access=access, context=context,
                           subject=request["agent_id"], adapter_id=request["adapter_id"])
    try:
        candidate = resolve_local_installation_selection(owner.candidates,
            adapter_id=request["adapter_id"], candidate_ref=request["candidate_ref"],
            expected_inventory_revision=request["inventory_revision"])
        if selected_fingerprint(candidate) != candidate.fingerprint:
            raise ValueError()
    except (CoreError, OSError, ValueError):
        raise _error("The selected local installation changed.") from None
    root = directory_identity(request["workspace_root"])
    home = directory_identity(request["provider_home"]) if request["provider_home"] is not None else None
    request_hash = _digest({"actor":context.actor_agent_id, "request":request})
    with factory.unit_of_work() as uow:
        if guard != _authority(uow, owner=owner, access=access, context=context,
                              subject=request["agent_id"], adapter_id=request["adapter_id"]):
            raise _error("The local realization authority changed during preparation.")
        conn = uow.connection
        current = conn.execute(
            "SELECT c.publication_sequence,c.inventory_revision,s.observation_age_ms "
            "FROM execution_inventory_current c JOIN execution_inventory_snapshots s "
            "ON s.server_id=c.server_id AND s.executor_id=c.executor_id AND s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?", (owner.key.server_id, executor_id)).fetchone()
        fresh = owner.fresh.get((owner.key.server_id, executor_id))
        if (current is None or fresh is None or fresh[0] != current["publication_sequence"]
                or current["inventory_revision"] != request["inventory_revision"]
                or current["observation_age_ms"] + (time.monotonic()-fresh[1])*1000 >= 120000):
            raise _error("Refresh the local inventory before preparing this realization.")
        prior = conn.execute(
            "SELECT * FROM execution_local_realizations WHERE server_id=? AND executor_id=? "
            "AND subject_agent_id=? AND client_intent_id=?",
            (owner.key.server_id,executor_id,request["agent_id"],request["client_intent_id"])).fetchone()
        if prior is not None:
            stored = json.loads(prior["local_record_json"])
            if prior["request_hash"] != request_hash:
                raise _error("The local intent ID has different content.")
            if stored["root"] != root or stored["provider_home"] != home or stored["candidate"] != asdict(candidate):
                raise _error("The approved local directory or installation changed.")
            publication = _persist_realization(uow, server_id=owner.key.server_id,
                executor_id=executor_id, agent_id=request["agent_id"], request=stored["publication"])
            return publication
        configuration = {"version":1,"server_id":owner.key.server_id,"executor_id":executor_id,
            "agent_id":request["agent_id"],"adapter_id":request["adapter_id"],"profile_revision":1,
            "local_consent_id":request["local_consent_id"],"provider_home":home,
            "secret_bindings":dict(request["secret_bindings"])}
        nonce = secrets.token_hex(24)
        public = {name:request[name] for name in ("client_intent_id","agent_id","workspace_id",
            "workspace_label","adapter_id","candidate_ref","inventory_revision","local_consent_id")}
        public.update(local_realization_ref="root_"+secrets.token_hex(16), realization_revision=1,
            configuration_digest=_digest(configuration),
            local_root_proof_digest=_digest({"root":root,"nonce":nonce,"agent_id":request["agent_id"],
                                             "server_id":owner.key.server_id,"executor_id":executor_id}))
        publication = _persist_realization(uow, server_id=owner.key.server_id,
            executor_id=executor_id, agent_id=request["agent_id"], request=public)
        record = {"root":root,"provider_home":home,"candidate":asdict(candidate),
                  "configuration":configuration,"root_proof_nonce":nonce,"publication":public}
        conn.execute(
            "INSERT INTO execution_local_realizations(server_id,executor_id,realization_ref,actor_agent_id,"
            "subject_agent_id,client_intent_id,request_hash,local_record_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (owner.key.server_id,executor_id,publication.realization_ref,context.actor_agent_id,
             request["agent_id"],request["client_intent_id"],request_hash,canonical_json(record).decode(),
             access.clock.now_iso()))
        access.authorize(context, uow=uow, audit=True, represented_agent_id=request["agent_id"])
        return publication
