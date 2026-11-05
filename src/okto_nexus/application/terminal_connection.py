"""Terminal setup facade over the existing operator HTTP setup contract."""
from urllib.parse import quote, urlencode
from copy import deepcopy
import hashlib
import json
import time
import uuid

from .project_preset import CLIENTS, ORIGIN, configuration, effects

PREFIX = '/api/v1/runtime-management'


def document_revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


class ConnectionError(Exception):
    def __init__(self, code, message, *, possible_effect=False, stage='connect'):
        self.code, self.message, self.possible_effect, self.stage = code, message, possible_effect, stage
        super().__init__(message)


class TerminalConnection:
    def __init__(self, call, save, *, monotonic=time.monotonic, sleep=time.sleep):
        self.call, self.save, self.monotonic, self.sleep = call, save, monotonic, sleep

    def api(self, method, path, body=None):
        return self.call(method, PREFIX + path, body)

    def options(self, request):
        subject = self.api('GET', '/connections/me')['agent_id'] if request.get('agent_creation') else request['agent_id']
        return self.api('GET', '/agents/' + quote(subject, safe='') + '/runtime-options?' +
            urlencode({'executor_id': request['executor_id'], **({'workspace_id': request['workspace_id']}
                       if request.get('workspace_id') else {})}))

    def current(self, agent, binding=None, *, new_agent_draft=False):
        query = dict(binding_id=binding) if binding else {}
        if new_agent_draft:
            query['new_agent_draft'] = 'true'
        return self.api('GET', '/connections/setup/' + quote(agent, safe='') +
                        ('?' + urlencode(query) if query else ''))

    def review(self, selection):
        me = self.api('GET', '/connections/me')
        creating = selection.get('create_agent', False)
        current = self.current(selection['agent'], new_agent_draft=creating)
        if creating and selection.get('binding_id'):
            raise ConnectionError('IDENTITY_REVIEW_CONFLICT', 'A new identity cannot adopt an existing binding.')
        binding = selection.get('binding_id')
        if binding:
            match = next((row for row in current['connections'] if row['binding_id'] == binding), None)
            if not match:
                raise ConnectionError('BINDING_UNAVAILABLE', 'The selected agent has no active connection with this binding ID.')
            if not selection['client']:
                selection['client'] = next((name for name, adapter in CLIENTS.items() if adapter == match['adapter_id']), None)
            if not selection['client']:
                raise ConnectionError('CLIENT_UNSUPPORTED', 'This binding has no supported project client.')
            return self._reused(selection, me['server_id'], binding)
        if current['connections']:
            # The agent was explicitly selected and the operator API has already
            # authorized these canonical bindings. Paths only select its local
            # destination; they never discover or create an agent identity.
            matches = []
            for row in current['connections'][:100]:
                if (row['execution_location'] != 'local' or row['adapter_id'] not in CLIENTS.values() or
                        selection['client'] and row['adapter_id'] != CLIENTS[selection['client']] or
                        selection.get('workspace_id') and row['workspace_id'] != selection['workspace_id'] or
                        selection.get('candidate_ref') and row['candidate_ref'] != selection['candidate_ref']):
                    continue
                existing = self.current(selection['agent'], row['binding_id'])
                if existing.get('folders', {}).get('workspace_root') == selection['project']:
                    matches.append(row)
            if len(matches) == 1 and len(current['connections']) <= 100:
                selected_binding = matches[0]
                selection['client'] = next(name for name, adapter in CLIENTS.items() if adapter == selected_binding['adapter_id'])
                return self._reused(selection, me['server_id'], selected_binding['binding_id'])
            raise ConnectionError('CONNECTION_SELECTION_REQUIRED',
                'This agent has no unique matching connection. Select --binding-id from its canonical connection list.')
        hosts, cursor = [], None
        for _ in range(10):
            page = self.api('GET', '/agents/' + quote(me['agent_id'] if creating else selection['agent'], safe='') + '/executors?' +
                urlencode({'limit': 100, **({'after_executor_id': cursor} if cursor else {})}))
            hosts.extend(row for row in page['items'] if row['kind'] == 'embedded')
            if not page['has_more']:
                break
            following = page['next_executor_id']
            if not following or following == cursor:
                raise ConnectionError('INVENTORY_UNCONFIRMED', 'The executor listing changed. Inspect the Server inventory.')
            cursor = following
        else:
            raise ConnectionError('INVENTORY_UNCONFIRMED', 'The executor listing exceeded its bounded page limit.')
        if len(hosts) != 1:
            raise ConnectionError('LOCAL_EXECUTOR_UNAVAILABLE', 'The selected Server has no unique local execution host.')
        request = {'client_intent_id': 'connect_' + uuid.uuid4().hex, 'agent_id': selection['agent'],
            'executor_id': hosts[0]['executor_id'], 'workspace_id': selection.get('workspace_id'), 'binding_id': None}
        if creating:
            request['agent_creation'] = {'display_name': '',
                'defaults_hash': current['agent_creation_defaults']['defaults_hash']}
        available = self.options(request)
        if not selection['client']:
            clients = {name for name, adapter in CLIENTS.items() for row in available['options']
                       if row['adapter_id'] == adapter and row.get('candidate_ref')}
            if len(clients) != 1:
                raise ConnectionError('CLIENT_SELECTION_REQUIRED',
                    'Choose --client from the observed harnesses: ' + ', '.join(sorted(clients)))
            selection['client'] = clients.pop()
        rows = [row for row in available['options'] if row['adapter_id'] == CLIENTS[selection['client']]
                and row.get('candidate_ref') and (not selection.get('candidate_ref') or
                                                 row['candidate_ref'] == selection['candidate_ref'])]
        if len(rows) != 1:
            raise ConnectionError('INSTALLATION_SELECTION_REQUIRED',
                'Select one observed installation with --candidate-ref; discovery does not prove provider login.')
        selected = rows[0]
        if not selected.get('can_configure'):
            raise ConnectionError('CONFIGURATION_NOT_AUTHORIZED', 'The canonical policy does not permit configuring this installation.')
        home = selection.get('provider_home') or selected.get('provider_home_suggestion')
        if selection['client'] == 'claude' and not home:
            raise ConnectionError('PROVIDER_HOME_REQUIRED', 'Pass --provider-home for the Claude login on this Server host.')
        selection['provider_home'] = home
        if creating:
            selection['display_name'] = selection.get('display_name') or (selection['client'].capitalize() + ' — ' + selection['label'])[:120]
            request['agent_creation']['display_name'] = selection['display_name']
            # Automatic work claiming is a separate opt-in, even if this Server
            # has enabled it globally. The initial review authorizes sessions.
            request['broadcast_handoff_auto_claim'] = False
        request.update(candidate_ref=selected['candidate_ref'], inventory_revision=available['inventory_revision'],
            baseline=current['baseline'], project_preset=dict(ORIGIN), configuration=configuration(
                adapter_id=selected['adapter_id'], project=selection['project'], label=selection['label'], provider_home=home))
        review = {'server_id': me['server_id'], 'selection': selection, 'request': request,
                  'version_check_required': selected['technical_state'] != 'READY_FOR_RUNTIME', 'effects': effects()}
        if creating:
            review['identity_creation'] = current['agent_creation_defaults'] | {'display_name': selection['display_name']}
            review['effects'].insert(0, 'Create this project identity at Finish with the reviewed coordination permissions; no global administration is granted.')
            review['effects'].append('Automatic handoff claiming is disabled for this new identity; work still requires canonical authorization.')
        document = dict(review, review_revision=document_revision(review), review_request=deepcopy(request), state='review', format=1)
        self.save(document)
        return document

    def _reused(self, selection, server_id, binding):
        document = {'format': 1, 'state': 'done', 'server_id': server_id, 'selection': selection,
                    'result': {'saved': True, 'agent_id': selection['agent'], 'binding': {'binding_id': binding}}}
        # Check the actual host/project before persisting the association.
        observed = self.observe(document)
        self.save(document)
        return observed

    def observe(self, document):
        me = self.api('GET', '/connections/me')
        if me['server_id'] != document['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The saved profile belongs to another Server installation.')
        selection = document['selection']
        binding = document['result'].get('binding', {}).get('binding_id')
        current = self.current(selection['agent'], binding)
        match = next((row for row in current['connections'] if row['binding_id'] == binding), None)
        if (not match or match['execution_location'] != 'local' or
                match['adapter_id'] != CLIENTS[selection['client']] or
                selection.get('workspace_id') and match['workspace_id'] != selection['workspace_id'] or
                selection.get('candidate_ref') and match['candidate_ref'] != selection['candidate_ref'] or
                selection.get('provider_home') is not None and
                    current.get('folders', {}).get('provider_home') != selection['provider_home'] or
                current.get('folders', {}).get('workspace_root') != selection['project']):
            raise ConnectionError('PROFILE_DRIFT', 'The canonical binding no longer matches this local project profile. Review it explicitly.')
        return {'state': 'configured', 'server_id': me['server_id'], 'agent_id': selection['agent'],
                'binding_id': binding, 'workspace_id': match['workspace_id'], 'configuration': current,
                'setup_run_id': document.get('request', {}).get('client_intent_id'),
                'session_state': 'not_checked', 'work_state': 'not_submitted'}

    def apply(self, document, *, approval=None, timeout=300):
        if self.api('GET', '/connections/me')['server_id'] != document['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The selected Server installation changed.')
        if document['state'] == 'done':
            return self.observe(document)
        review = {key: document[key] for key in ('server_id', 'selection', 'version_check_required', 'effects')}
        if 'identity_creation' in document:
            review['identity_creation'] = document['identity_creation']
        review['request'] = document['review_request']
        original = document['review_request']
        if (document_revision(review) != document['review_revision'] or
                (document['request'] | {'inventory_revision': original['inventory_revision']}) != original):
            raise ConnectionError('REVIEW_CHANGED', 'The saved setup no longer matches its reviewed configuration.')
        if document['state'] == 'review':
            if approval != document_revision(review) or approval != document['review_revision']:
                raise ConnectionError('REVIEW_REQUIRED', 'Approve the displayed review revision before applying setup.')
            document['state'] = 'approved'
            self.save(document)
        request = document['request']
        if document['state'] in ('test_submitted', 'finish'):
            try:
                receipt = self.api('POST', '/connections/setup:recover', request)
            except ConnectionError as error:
                if (error.code, error.stage) != ('NOT_FOUND', 'connection.setup_commit'):
                    raise
            else:
                if (receipt.get('setup_run_id') != request['client_intent_id'] or receipt.get('state') != 'committed'
                        or receipt.get('result', {}).get('agent_id') != request['agent_id']):
                    raise ConnectionError('RECEIPT_UNCONFIRMED', 'The Server returned an inconsistent setup receipt.', possible_effect=True)
                document.update(state='done', result=receipt['result'])
                self.save(document)
                return self.observe(document)
        if (document['state'] in ('approved', 'check_submitted') and document['version_check_required']
                and not document.get('version_check_confirmed')):
            if document['state'] == 'approved':
                document['state'] = 'check_submitted'
                self.save(document)
                self.api('POST', '/runtime/executors/' + quote(request['executor_id'], safe='') + '/installations:check',
                    dict(agent_id=self.api('GET', '/connections/me')['agent_id'] if request.get('agent_creation') else request['agent_id'],
                         adapter_id=request['configuration']['adapter_id'],
                         candidate_ref=request['candidate_ref'], inventory_revision=request['inventory_revision'], approved=True))
            available = self.options(request)
            selected = next((row for row in available['options'] if row['candidate_ref'] == request['candidate_ref']
                             and row['adapter_id'] == request['configuration']['adapter_id']), None)
            if not selected or selected['technical_state'] != 'READY_FOR_RUNTIME':
                state = selected['technical_state'] if selected else 'SELECTION_CHANGED'
                reasons = ', '.join(selected.get('technical_reasons', [])) if selected else ''
                raise ConnectionError('INSTALLATION_UNCONFIRMED',
                    f'The reviewed installation is {state} ({reasons}). Its version command was not repeated.', possible_effect=True)
            request['inventory_revision'] = available['inventory_revision']
            document.update(state='approved', version_check_confirmed=True)
            self.save(document)
        if document['state'] == 'approved':
            document['state'] = 'test_submitted'
            self.save(document)
            test = self.api('POST', '/connections/setup:test', request)
        elif document['state'] == 'test_submitted':
            try:
                test = self.api('GET', '/connections/setup-tests/' + quote(request['client_intent_id'], safe=''))
            except ConnectionError:
                raise ConnectionError('SETUP_TEST_UNCONFIRMED', 'The prior test result is unavailable. No new model turn was sent.', possible_effect=True) from None
        elif document['state'] == 'finish':
            test = {'status': 'succeeded'}  # Finish rechecks its canonical test or existing commit.
        else:
            raise ConnectionError('CHECKPOINT_INVALID', 'The saved setup checkpoint is not recognized.')
        deadline = self.monotonic() + timeout
        while test['status'] == 'running' and self.monotonic() < deadline:
            self.sleep(min(1, max(0, deadline - self.monotonic())))
            test = self.api('GET', '/connections/setup-tests/' + quote(request['client_intent_id'], safe=''))
        if test['status'] != 'succeeded':
            return {'state': 'test_' + test['status'], 'setup_run_id': request['client_intent_id'],
                    'test': test, 'work_state': 'not_submitted'}
        document['state'] = 'finish'
        self.save(document)
        result = self.api('POST', '/connections/setup:finish', request)
        document.update(state='done', result=result)
        self.save(document)
        return self.observe(document)
