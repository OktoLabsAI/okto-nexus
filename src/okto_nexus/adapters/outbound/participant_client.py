"""Origin-bound existing agent credentials, without operator/session fallback."""
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, build_opener

from ...application.terminal_connection import ConnectionError
from ...domain.keys import is_well_formed_api_key
from .operator_client import server_origin
from .provider_vault import open_backend
from .service_manager.inspection import NoRedirect


def participant_key(value):
    if not is_well_formed_api_key(value):
        raise ConnectionError('PARTICIPANT_KEY_REQUIRED', 'Supply an existing participant nxs_ key through hidden input, stdin or the explicitly selected environment variable.')
    return value


class ParticipantHTTP:
    def __init__(self, origin, key, agent_id, *, timeout=15):
        self.origin, self.key, self.agent_id = server_origin(origin), participant_key(key), agent_id
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def context(self, workspace_id):
        request = Request(self.origin + '/v1/connections/participant?' + urlencode(dict(workspace_id=workspace_id)),
            headers={'Authorization': 'Bearer ' + self.key, 'X-Nexus-Agent-Hint': self.agent_id,
                     'Accept': 'application/json'}, method='GET')
        failed = False
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response, failed = error, True
            with response:
                raw = response.read(262145)
                status = response.status if hasattr(response, 'status') else response.code if hasattr(response, 'code') else 200
        except (HTTPException, URLError, TimeoutError, OSError):
            raise ConnectionError('SERVER_UNREACHABLE', 'The selected Server could not be checked. No local Server was started.') from None
        if 300 <= status < 400:
            raise ConnectionError('SERVER_REDIRECT_REFUSED', 'Select the final approved Server origin explicitly; credentials are never redirected.')
        if len(raw) > 262144 or self.key.encode() in raw:
            raise ConnectionError('RESPONSE_UNCONFIRMED', 'The participant response is unsafe or oversized.')
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise ConnectionError('RESPONSE_UNCONFIRMED', 'The Server returned an invalid participant response.') from None
        if failed:
            error = value.get('error')
            code = error.get('code') if isinstance(error, dict) else None
            code = code if isinstance(code, str) and re.fullmatch('[A-Z_]{1,60}', code) else 'REQUEST_REFUSED'
            if status == 404 and code != 'NOT_FOUND':
                code = 'SERVER_UPGRADE_REQUIRED'
            raise ConnectionError(code, 'The Server refused participant preparation. Check the existing identity, workspace, credential and MCP policy.')
        if (value.get('participant_setup_revision') != 1 or value.get('agent_id') != self.agent_id or
                not isinstance(value.get('workspace'), dict) or
                value['workspace'].get('workspace_id') != workspace_id or
                not isinstance(value.get('server_id'), str) or not value['server_id'] or
                value.get('mcp_enabled') is not True or
                not isinstance(value.get('review_revision'), str)):
            raise ConnectionError('PARTICIPANT_CONTEXT_UNCONFIRMED', 'The Server did not confirm the requested participant and workspace. Upgrade or inspect this Server.')
        return value


class ParticipantVault:
    def __init__(self, home, profile, review, *, backend=None):
        identity = [os.path.normcase(str(Path(home).resolve())), profile, review['origin'],
                    review['context']['server_id'], review['context']['agent_id'], review['setup_run_id']]
        self.service = 'okto-nexus/participant/' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        self.backend = backend

    def call(self, action, value=None):
        try:
            backend = self.backend or open_backend()
            if action == 'store':
                backend.set(self.service, 'agent-key', participant_key(value))
            else:
                return participant_key(backend.get(self.service, 'agent-key'))
        except Exception:
            raise ConnectionError('PARTICIPANT_VAULT_UNAVAILABLE', 'The protected participant credential is unavailable. Unlock the OS vault or supply the existing key again; no plaintext fallback is used.') from None
