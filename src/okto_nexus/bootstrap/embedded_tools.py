"""Serve-owned tool credentials persisted before approved native configuration."""
import asyncio
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlsplit

from nexus_connector_core import CoreError
from nexus_connector_core.harness_config import harness_http_template
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.provider_vault import open_backend
from ..application.execution_capabilities import ExecutionCapabilityService
from ..domain.runtime_context import RuntimeRequestContext

MCP_ACTIONS=("tools/call","resources/read","prompts/get","agent_whoami",
    "handoff_list_available","handoff_get","handoff_claim","handoff_complete",
    "event_cursor","event_get","event_wait","runtime_input_list","runtime_input_respond","message_create")


class SessionToolVault:
    def __init__(self, home):
        self.service="okto-nexus/session-tools/"+hashlib.sha256(os.path.normcase(str(home.resolve())).encode()).hexdigest()
    def store(self, request_id, secret):
        try:
            if not isinstance(secret,str) or not secret.startswith("nxc4_"):
                raise ValueError()
            open_backend().set(self.service,request_id,secret)
        except Exception:
            raise CoreError("AGENT_AUTH_REQUIRED","local_tool_vault") from None
    def remove(self, request_id):
        try:
            open_backend().remove(self.service,request_id)
        except Exception:
            raise CoreError("AGENT_AUTH_REQUIRED","local_tool_vault") from None


class EmbeddedToolsOwner:
    def __init__(self, owner):
        self.owner=owner
        self.vault=SessionToolVault(owner.deps.config.home_dir)
        self.tasks={}
        self.configurations={}
        self.stored=set()
        self.pending_removal=set()
        self.closed=False

    @property
    def origin(self):
        return getattr(self.owner.deps,"runtime_owner_api_url",None)

    def _stage(self, frame, audience, actions):
        key=tuple(frame[k] for k in ("server_id","executor_id","session_id"))
        digest=hashlib.sha256(canonical_json(dict(scope={k:frame[k] for k in (
            "server_id","executor_id","session_id","operation_id","intent_hash")},audience=audience,actions=list(actions)))).hexdigest()
        with self.owner.factory.unit_of_work() as uow:
            self.owner.verify(uow=uow)
            row=uow.connection.execute("SELECT * FROM execution_local_tool_credentials "
                "WHERE server_id=? AND executor_id=? AND session_id=?",key).fetchone()
            if row is not None:
                # A restarted owner may not infer delivery or a new lifetime.
                raise CoreError("RECONCILIATION_REQUIRED","local_tool_credential")
            request_id="localcap_"+secrets.token_hex(16)
            uow.connection.execute("INSERT INTO execution_local_tool_credentials "
                "(server_id,executor_id,session_id,request_id,request_digest,status) VALUES (?,?,?,?,?,'REQUESTED')",
                (*key,request_id,digest))
            agent=uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id=? AND is_active=1",
                (frame["agent_id"],)).fetchone()
            if agent is None or not agent[0]:
                raise CoreError("AGENT_AUTH_REQUIRED","local_tool_credential")
            return request_id,RuntimeRequestContext(frame["agent_id"],"agent_key",credential_binding=agent[0])

    async def prepare(self, frame, launch):
        if self.origin is None:
            return  # Embedders without a served address cannot render HTTP tools.
        if self.closed:
            raise CoreError("STALE_GENERATION","local_tools")
        session_id=frame["session_id"]
        fingerprint=hashlib.sha256(canonical_json(frame)).hexdigest()
        cached=self.tasks.get(session_id)
        if cached is None:
            if len(self.tasks)>=128:
                raise CoreError("CAPACITY_EXCEEDED","local_tools")
            task=asyncio.create_task(self._prepare(frame,launch),name="embedded-tool-credential")
            task.add_done_callback(lambda done:None if done.cancelled() else done.exception())
            self.tasks[session_id]=(fingerprint,task)
        else:
            if cached[0]!=fingerprint:
                raise CoreError("OPERATION_CONFLICT","local_tools")
            task=cached[1]
        await asyncio.shield(task)
        await asyncio.to_thread(self.owner.verify)

    async def _prepare(self, frame, launch):
        await asyncio.to_thread(launch.check)
        adapter=launch.candidate.adapter_id
        native=adapter=="pi_rpc"
        with self.owner.factory.unit_of_work(write=False) as uow:
            row=uow.connection.execute("SELECT ep.public_config FROM execution_bindings b JOIN agent_endpoints ep USING(endpoint_id) "
                "WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=?",
                tuple(frame[k] for k in ('server_id','executor_id','binding_id'))).fetchone()
            always_allow = bool(row and json.loads(row[0]).get('nexus_tool_permission') == 'always_allow')
        if not native and adapter not in ("codex_app_server","claude_stream"):
            raise CoreError("CAPABILITY_UNSUPPORTED","local_tools")
        provider_home_http=not native and launch.record["provider_home"] is not None and not launch.auth_refs
        process_http=not native and (provider_home_http or always_allow)
        audience="nexus-native-session" if native else "nexus-mcp-session"
        actions=("handoff.get","handoff.claim","handoff.complete","runtime.input.list","runtime.input.respond","message.create") if native else MCP_ACTIONS
        request_id,context=await asyncio.to_thread(self._stage,frame,audience,actions)
        service=ExecutionCapabilityService(factory=self.owner.factory,access=self.owner.access)
        start=time.monotonic()
        cap=await asyncio.to_thread(service.issue,context=context,session_id=frame["session_id"],
            request=dict(capability_request_id=request_id,binding_id=frame["binding_id"],audience=audience,actions=list(actions)),
            mcp_url=self.origin.rstrip("/")+"/mcp",owner_guard=lambda uow:self.owner.verify(uow=uow))
        await asyncio.to_thread(self.vault.store,request_id,cap["capability"])
        self.stored.add(request_id)
        def persisted():
            with self.owner.factory.unit_of_work() as uow:
                self.owner.verify(uow=uow)
                uow.connection.execute("UPDATE execution_local_tool_credentials SET status='STORED',metadata_json=? "
                    "WHERE request_id=? AND status='REQUESTED'",
                    (canonical_json({k:v for k,v in cap.items() if k not in ("capability","expires_in")}).decode(),request_id))
        await asyncio.to_thread(persisted)
        await asyncio.to_thread(launch.check)
        deadline=start+cap["expires_in"]-.5
        if deadline<=time.monotonic():
            raise CoreError("AUTH_EXPIRED","local_tools")
        home,template,native_factory=None,None,None
        if native:
            from nexus_connector_core.native_action_bridge import NativeActionGrant
            from ..adapters.outbound.execution.core_native_actions import embedded_native_action_owner_factory
            scope=cap["scope"]
            grant=NativeActionGrant(cap["capability_ref"],scope["server_id"],scope["executor_id"],scope["binding_id"],
                scope["agent_id"],scope["workspace_id"],scope["session_id"],self.owner.channel.connection_generation,
                scope["authorization_revision"],scope["configuration_revision"],deadline,frozenset(actions),scope,
                self.owner.channel.connection_id)
            async def metadata():
                await asyncio.to_thread(self.owner.verify)
                await asyncio.to_thread(launch.check)
                sent_at=time.monotonic()
                result=await asyncio.to_thread(service.describe,context=context,session_id=scope["session_id"],
                    binding_id=scope["binding_id"],capability_id=cap["capability_id"],
                    request_id="capmeta_"+secrets.token_hex(16),mcp_url=self.origin.rstrip("/")+"/mcp")
                await asyncio.to_thread(self.owner.verify)
                await asyncio.to_thread(launch.check)
                return result,sent_at+result["expires_in"]-.5
            native_factory=embedded_native_action_owner_factory(self.owner.deps,grant,cap["capability"],
                                                                  metadata_provider=metadata)
        else:
            from .local_mcp_home import session_mcp_home
            loopback=urlsplit(self.origin).hostname in ("127.0.0.1","localhost","::1")
            entry_name="nexus_"+hashlib.sha256(cap["capability_ref"].encode()).hexdigest()[:16] if process_http else "nexus"
            template=harness_http_template(adapter,cap["mcp_url"],cap["capability_ref"],entry_name=entry_name,
                approved_origins={self.origin},harness_is_local=loopback,loopback_reachable=loopback,format_qualified=True,
                always_allow_tools=always_allow)
            if not provider_home_http:
                home=await asyncio.to_thread(session_mcp_home,self.owner.deps.config.home_dir/"session-mcp",
                    frame=frame,configuration_digest=launch._snapshot,template=template)
        self.configurations[frame["session_id"]]=dict(cap=cap,deadline=deadline,home=home,template=template,
            request_id=request_id,native_factory=native_factory,snapshot=launch._snapshot,process_http=process_http)

    def decorate(self, launch):
        config=self.configurations.get(launch.scope["session_id"])
        if config is None:
            if self.origin is not None:
                raise CoreError("RECONCILIATION_REQUIRED","local_tool_configuration")
            return launch
        if config["cap"]["scope"]!=launch.scope or config["snapshot"]!=launch._snapshot:
            raise CoreError("PROFILE_DRIFT","local_tool_configuration")
        launch.tools=config
        launch.auth_refs=tuple(sorted((*launch.auth_refs,config["cap"]["capability_ref"])))
        return launch

    async def release_session(self, session_id):
        config=self.configurations.get(session_id)
        if config is None:
            return
        await self._remove(config["request_id"])
        self.configurations.pop(session_id,None)
        self.tasks.pop(session_id,None)

    async def _remove(self, request_id):
        if request_id in self.stored:
            await asyncio.to_thread(self.vault.remove,request_id)
            self.stored.discard(request_id)
            self.pending_removal.add(request_id)
        if request_id not in self.pending_removal:
            return
        # Retry metadata after an OS removal without deleting material twice.
        def removed():
            with self.owner.factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_local_tool_credentials SET status='REMOVED' WHERE request_id=?",
                    (request_id,))
        await asyncio.to_thread(removed)
        self.pending_removal.discard(request_id)

    async def close(self, *, release):
        self.closed=True
        await asyncio.shield(asyncio.gather(*(task for _,task in self.tasks.values()),return_exceptions=True))
        if release:
            for request_id in tuple(self.stored|self.pending_removal):
                await self._remove(request_id)
