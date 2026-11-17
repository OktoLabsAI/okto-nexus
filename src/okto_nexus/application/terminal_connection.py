"""Terminal setup facade over the existing operator HTTP setup contract."""
from urllib.parse import quote, urlencode
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import time
import uuid

from .project_preset import CLIENTS, ORIGIN, configuration, effects

PREFIX = '/api/v1/runtime-management'


def document_revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def _same_local_path(actual, selected):
    # Windows accepts both separators, while the Server returns its native one.
    # Do not resolve links, fold case, collapse '..', or inspect a provider home.
    return (isinstance(actual, str) and isinstance(selected, str)
            and os.path.isabs(actual) and os.path.isabs(selected)
            and actual.replace('/', os.sep) == selected.replace('/', os.sep))


class ConnectionError(Exception):
    def __init__(self, code, message, *, possible_effect=False, stage='connect', choices=None):
        self.code, self.message, self.possible_effect, self.stage = code, message, possible_effect, stage
        self.choices = choices
        super().__init__(message)


class TerminalConnection:
    def __init__(self, call, save, *, monotonic=time.monotonic, sleep=time.sleep):
        self.call, self.save, self.monotonic, self.sleep = call, save, monotonic, sleep

    def api(self, method, path, body=None):
        return self.call(method, PREFIX + path, body)

    def options(self, request, *, deadline=None, server_id=None):
        if deadline is not None:
            self._check_observation_deadline(deadline)
        subject = request['agent_id']
        if request.get('agent_creation'):
            me = self.api('GET', '/connections/me')
            if server_id is not None and me['server_id'] != server_id:
                raise ConnectionError('SERVER_ID_MISMATCH', 'The selected Server installation changed.', possible_effect=True)
            subject = me['agent_id']
        if deadline is not None:
            self._check_observation_deadline(deadline)
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
        if selection.get('setup_intent_id') and (binding or current['connections']):
            raise ConnectionError('ADDITION_CONFLICT',
                'Adding a connection cannot resume or replace this existing binding. Resume it explicitly or review a separate project identity.')
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
        request = {'client_intent_id': selection.get('setup_intent_id') or 'connect_' + uuid.uuid4().hex, 'agent_id': selection['agent'],
            'executor_id': hosts[0]['executor_id'], 'workspace_id': selection.get('workspace_id'), 'binding_id': None}
        if creating:
            request['agent_creation'] = {'display_name': '',
                'defaults_hash': current['agent_creation_defaults']['defaults_hash']}
        available = self.options(request)
        if selection['client'] not in CLIENTS:
            clients = {name for name, adapter in CLIENTS.items() for row in available['options']
                       if row['adapter_id'] == adapter and row.get('candidate_ref')}
            if selection['client'] is not None or len(clients) != 1:
                raise ConnectionError('CLIENT_SELECTION_REQUIRED',
                    'Choose a supported harness from the passive inventory.',
                    choices=sorted(clients))
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
        if selection.get('public_connection') is not None:
            # Product metadata belongs in the setup envelope, outside the Core
            # configuration schema. Its stable ref and root proof were reviewed.
            request['public_connection'] = deepcopy(selection['public_connection'])
        native_policy = current.get('native_decision_policy')
        if native_policy is None:
            raise ConnectionError('NATIVE_POLICY_UNCONFIRMED', 'This Server cannot review native decision policy for project setup.')
        if native_policy['value'] is not True and not native_policy['can_initialize']:
            raise ConnectionError('NATIVE_DECISIONS_DISABLED',
                'Native decisions are disabled by an existing Server policy (' + native_policy['source'] +
                '). Project setup preserves it; an authorized policy change is required before this route can be used.')
        request['native_decision_policy'] = dict(expected_revision=native_policy['revision'],
                                                initialize=native_policy['can_initialize'])
        review = {'server_id': me['server_id'], 'selection': selection, 'request': request,
                  'version_check_required': selected['technical_state'] != 'READY_FOR_RUNTIME', 'effects': effects()}
        if native_policy['can_initialize']:
            review['effects'].append('Enable Server-wide human review (feature_hitl) at Finish for native decisions and matching coordination approval rules. Each decision still requires its authorized recipient; no permission is approved automatically.')
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

    def review_public_association(self, selection, *, previous=None):
        """Review legacy adoption as metadata, never as a new setup Test."""
        from dataclasses import fields
        from ..domain.quick_connect import CanonicalConnectionReference
        me = self.api('GET', '/connections/me')
        legacy = deepcopy(selection)
        public = legacy.pop('public_connection')
        binding = self.api('GET', '/connections/bindings/' + quote(selection['binding_id'], safe=''))
        # Validate the existing connection/root/provider/exact selectors before
        # preparing its public metadata review. No shortcut is saved yet.
        temporary = dict(server_id=me['server_id'], selection=legacy,
            result=dict(binding=dict(binding_id=selection['binding_id'])))
        if isinstance(self, RemoteTerminalConnection):
            temporary['remote_scope'] = {key: binding[key] for key in self.SCOPE}
        self.observe(temporary)
        reference = {field.name: binding.get(field.name) for field in fields(CanonicalConnectionReference)}
        CanonicalConnectionReference(**reference)
        request = dict(approved=True, client_intent_id='associate_' + uuid.uuid4().hex,
            connect_id=public['connect_id'], expected_binding_ref=reference,
            expected_binding_revision=binding['binding_revision'])
        review = dict(server_id=me['server_id'], selection=selection, request=request,
            version_check_required=False,
            effects=['Associate this public Harness ID with the exact existing connection.',
                'No installation check, model test, agent creation, grant renewal or new session.'])
        if 'remote_scope' in temporary:
            review['remote_scope'] = temporary['remote_scope']
        document = deepcopy(previous) if previous else {}
        if previous:
            document['public_id_previous_setup'] = {key: deepcopy(previous[key])
                for key in ('request', 'review_request', 'review_revision', 'result', 'selection') if key in previous}
        document.update(review, format=1, kind='public_id_association', state='review',
            review_request=deepcopy(request), review_revision=document_revision(review))
        self.save(document)
        return document

    def _apply_public_association(self, document, approval):
        review = {key: document[key] for key in ('server_id', 'selection', 'request', 'version_check_required', 'effects')}
        if 'remote_scope' in document:
            review['remote_scope'] = document['remote_scope']
        if document_revision(review) != document['review_revision'] or document['request'] != document['review_request']:
            raise ConnectionError('REVIEW_CHANGED', 'The public Harness ID association review changed.')
        if document['state'] == 'review':
            if approval != document['review_revision']:
                raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact public Harness ID association review.')
            document['state'] = 'association_submitted'
            self.save(document)
        if document['state'] != 'association_submitted':
            raise ConnectionError('CHECKPOINT_INVALID', 'The retained association checkpoint is unrecognized.')
        public = self.api('POST', '/connections/public-ids/associate-existing', document['request'])
        if (public.get('state') != 'bound' or public.get('connect_id') != document['request']['connect_id']
                or public.get('canonical_ref') != document['request']['expected_binding_ref']):
            raise ConnectionError('PUBLIC_ID_UNCONFIRMED', 'The public association result is inconsistent.', possible_effect=True)
        document.update(state='done', result=dict(saved=True, agent_id=document['selection']['agent'],
            binding=dict(binding_id=document['selection']['binding_id']), public_connection=public))
        previous_selection = document.get('public_id_previous_setup', {}).get('selection')
        if previous_selection:
            document['selection'] = deepcopy(previous_selection) | document['selection']
        self._save_committed(document)
        return self.observe(document)

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
                    not _same_local_path(current.get('folders', {}).get('provider_home'), selection['provider_home']) or
                current.get('folders', {}).get('workspace_root') != selection['project']):
            raise ConnectionError('PROFILE_DRIFT', 'The canonical binding no longer matches this local project profile. Review it explicitly.')
        result = {'state': 'configured', 'server_id': me['server_id'], 'agent_id': selection['agent'],
                'binding_id': binding, 'workspace_id': match['workspace_id'], 'configuration': current,
                'setup_run_id': document.get('request', {}).get('client_intent_id'),
                'session_state': 'not_checked', 'work_state': 'not_submitted'}
        public = document.get('result', {}).get('public_connection') or selection.get('public_connection')
        if public is not None:
            result['public_connection'] = self._observe_public_id(public['connect_id'],
                workspace_id=match['workspace_id'], binding_id=binding, server_id=me['server_id'])
        return result

    def _observe_public_id(self, connect_id, *, workspace_id, binding_id, server_id):
        from dataclasses import fields
        from ..domain.quick_connect import CanonicalConnectionReference, normalize_connect_id
        # Full binding + public registry are independent canonical reads. Their
        # complete immutable references must agree before saying "connected".
        binding = self.api('GET', '/connections/bindings/' + quote(binding_id, safe=''))
        page = self.api('GET', '/connections/public-ids?' + urlencode(dict(
            workspace_id=workspace_id, connect_id=normalize_connect_id(connect_id), limit=100)))
        rows = [r for r in page.get('items', ()) if r.get('connect_id') == connect_id]
        reference = {field.name: binding.get(field.name) for field in fields(CanonicalConnectionReference)}
        if (page.get('server_id') != server_id or page.get('has_more') is not False
                or page.get('total_is_exact') is not True or len(rows) != 1
                or rows[0].get('state') != 'bound' or binding.get('state') != 'APPROVED'
                or reference['server_id'] != server_id or reference['workspace_id'] != workspace_id
                or reference['binding_id'] != binding_id
                or any(type(value) is not str or not value for value in reference.values())
                or rows[0].get('canonical_ref') != reference):
            raise ConnectionError('PUBLIC_ID_UNCONFIRMED',
                'The public Harness ID is not bound to the exact approved connection.')
        return dict(version=1, state='bound', connect_id=connect_id, canonical_ref=reference)

    def approve_review(self, document, approval):
        review = {key: document[key] for key in ('server_id', 'selection', 'version_check_required', 'effects')}
        for key in ('identity_creation', 'preset_review'):
            if key in document:
                review[key] = document[key]
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
        return document['request']

    def _check_observation_deadline(self, deadline):
        if self.monotonic() >= deadline:
            raise ConnectionError('INSTALLATION_UNCONFIRMED',
                'The reviewed installation was not confirmed within the observation deadline. '
                'Resume the same saved request; its version command was not repeated.', possible_effect=True)

    def _confirm_version_check(self, document, request, deadline):
        """Observe the saved selection; a lost check reply never repeats its probe."""
        adapter = request['configuration']['adapter_id']
        while self.monotonic() < deadline:
            try:
                if self.api('GET', '/connections/me')['server_id'] != document['server_id']:
                    raise ConnectionError('SERVER_ID_MISMATCH', 'The selected Server installation changed.')
                available = self.options(request, deadline=deadline, server_id=document['server_id'])
            except ConnectionError as error:
                if error.code != 'SERVER_UNREACHABLE' or error.possible_effect:
                    # A read refusal does not undo the previously submitted check.
                    raise ConnectionError(error.code, error.message,
                        possible_effect=True, stage=error.stage) from None
            else:
                if available['executor_id'] != request['executor_id']:
                    raise ConnectionError('EXECUTOR_ID_MISMATCH', 'The observed executor changed.', possible_effect=True)
                selected = [row for row in available['options']
                            if row['candidate_ref'] == request['candidate_ref'] and row['adapter_id'] == adapter]
                if len(selected) != 1:
                    raise ConnectionError('INSTALLATION_UNCONFIRMED',
                        'The reviewed installation selection changed. Its version command was not repeated.', possible_effect=True)
                selected = selected[0]
                fresh = available.get('adapter_freshness', {}).get(adapter) == 'FRESH'
                if fresh and selected.get('can_configure') is not True:
                    raise ConnectionError('CONFIGURATION_NOT_AUTHORIZED',
                        'The canonical policy no longer permits configuring this installation.', possible_effect=True)
                if fresh and selected['technical_state'] == 'READY_FOR_RUNTIME':
                    # A bounded HTTP call can finish after the overall observation deadline.
                    if self.monotonic() >= deadline:
                        break
                    request['inventory_revision'] = available['inventory_revision']
                    document.update(state='approved', version_check_confirmed=True)
                    self.save(document)
                    return
            remaining = deadline - self.monotonic()
            if remaining > 0:
                self.sleep(min(1, remaining))
        raise ConnectionError('INSTALLATION_UNCONFIRMED',
            'The reviewed installation was not confirmed before the observation deadline. '
            'Resume the same saved request; its version command was not repeated.', possible_effect=True)

    def apply(self, document, *, approval=None, timeout=300):
        check_deadline = self.monotonic() + timeout
        check_submitted = document['state'] == 'check_submitted'
        try:
            me = self.api('GET', '/connections/me')
        except ConnectionError as error:
            if not check_submitted:
                raise
            raise ConnectionError(error.code, error.message, possible_effect=True, stage=error.stage) from None
        if me['server_id'] != document['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The selected Server installation changed.', possible_effect=check_submitted)
        if document['state'] == 'done':
            return self.observe(document)
        if document.get('kind') == 'public_id_association':
            return self._apply_public_association(document, approval)
        request = self.approve_review(document, approval)
        checked_version = False
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
                self._save_committed(document)
                return self.observe(document)
        if (document['state'] in ('approved', 'check_submitted') and document['version_check_required']
                and not document.get('version_check_confirmed')):
            if document['state'] == 'approved':
                document['state'] = 'check_submitted'
                self.save(document)
                self._check_observation_deadline(check_deadline)
                subject = request['agent_id']
                if request.get('agent_creation'):
                    me = self.api('GET', '/connections/me')
                    if me['server_id'] != document['server_id']:
                        raise ConnectionError('SERVER_ID_MISMATCH', 'The selected Server installation changed.', possible_effect=True)
                    subject = me['agent_id']
                self._check_observation_deadline(check_deadline)
                try:
                    self.api('POST', '/runtime/executors/' + quote(request['executor_id'], safe='') + '/installations:check',
                        dict(agent_id=subject,
                             adapter_id=request['configuration']['adapter_id'],
                             candidate_ref=request['candidate_ref'], inventory_revision=request['inventory_revision'], approved=True))
                except ConnectionError as error:
                    if error.code != 'OUTCOME_UNKNOWN' or error.possible_effect is not True:
                        raise
            self._confirm_version_check(document, request, check_deadline)
            # Persisting the confirmation can also exhaust the check's budget.
            # The confirmed checkpoint remains resumable, but no new test starts now.
            self._check_observation_deadline(check_deadline)
            checked_version = True
        if request.get('public_connection') and document['state'] == 'approved':
            # Reserving after version confirmation fixes the current request
            # hash. It precedes the paid model Test and is idempotent by intent.
            reservation = self.api('POST', '/connections/public-ids/reserve',
                dict(approved=True, request=deepcopy(request)))
            public = request['public_connection']
            if (reservation.get('version') != 1 or reservation.get('state') not in ('reserved', 'bound')
                    or reservation.get('connect_id') != public['connect_id']
                    or reservation.get('reservation_ref') != public['reservation_ref']
                    or reservation.get('setup_run_id') != request['client_intent_id']):
                raise ConnectionError('PUBLIC_ID_RESERVATION_UNCONFIRMED',
                    'The Harness ID reservation was not confirmed. Preserve this intent.', possible_effect=True)
            document['public_id_reservation'] = reservation
            self.save(document)
            if reservation['state'] == 'bound':
                receipt = self.api('POST', '/connections/setup:recover', request)
                if (receipt.get('state') != 'committed' or receipt.get('setup_run_id') != request['client_intent_id']
                        or receipt.get('result', {}).get('public_connection', {}).get('connect_id') != public['connect_id']
                        or receipt.get('result', {}).get('agent_id') != request['agent_id']):
                    raise ConnectionError('RECEIPT_UNCONFIRMED', 'The bound Harness ID has no matching setup receipt.', possible_effect=True)
                document.update(state='done', result=receipt['result'])
                self._save_committed(document)
                return self.observe(document)
        if document['state'] == 'approved':
            document['state'] = 'test_submitted'
            self.save(document)
            if checked_version:
                # Preserve the submitted checkpoint even when its durable write
                # used the remaining time. Recovery must not replay a missing test.
                self._check_observation_deadline(check_deadline)
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
            result = {'state': 'test_' + test['status'], 'setup_run_id': request['client_intent_id'],
                      'test': test, 'work_state': 'not_submitted'}
            if test['status'] == 'failed' and 'PROVIDER_AUTH_REQUIRED' in test.get('details', []):
                home = request['configuration']['provider_home']
                result['error_code'] = 'PROVIDER_AUTH_REQUIRED'
                if request['configuration']['adapter_id'] == 'codex_app_server':
                    if home:
                        action = 'On the Server host, use the approved provider_home: ' + home + '. Set HOME to ' + home + '. '
                        if Path(home).name == '.codex':
                            action += 'Set CODEX_HOME to ' + home + '. '
                        else:
                            action += ('Set CODEX_HOME to ' + home + ' if it already contains auth.json or config.toml, '
                                'or is the discovered Codex state directory; otherwise set CODEX_HOME to ' + str(Path(home) / '.codex') + '. ')
                    else:
                        action = ('Review setup with --provider-home selecting the provider login home on the Server host. '
                            'Set HOME to that selected home. Set CODEX_HOME to the selected home if it is named .codex, '
                            'contains auth.json or config.toml, or is the discovered Codex state directory; otherwise use its .codex subdirectory. ')
                    action += 'Then run codex login in your terminal. '
                else:
                    action = (
                        'Complete provider sign-in locally on the Server host using the approved provider_home: ' + home + '. '
                        if home else 'Review setup with --provider-home selecting the provider login home on the Server host, '
                                     'and complete provider sign-in there. '
                    )
                result['next_action'] = action + 'Then explicitly review setup with a new --profile before approving another connection test. No login or new test was started; this saved request will not be replayed.'
            return result
        document['state'] = 'finish'
        self.save(document)
        result = self.api('POST', '/connections/setup:finish', request)
        document.update(state='done', result=result)
        self._save_committed(document)
        return self.observe(document)

    def _save_committed(self, document):
        try:
            self.save(document)
        except OSError:
            # The previous durable checkpoint still owns this same setup intent;
            # recovery reads its receipt and repairs only the local shortcut.
            public = document.get('result', {}).get('public_connection')
            error = ConnectionError('CONFIGURED_SHORTCUT_PENDING',
                'The canonical connection is configured; its local shortcut needs repair. Resume the same profile.',
                possible_effect=True)
            error.committed_public_connection = public
            raise error from None


class RemoteTerminalConnection(TerminalConnection):
    """Associate an operator's local shortcut with an already approved binding.

    Project paths in this profile are local shortcuts, never remote launch paths.
    Connector discovery and setup continue to own the execution host mapping.
    """
    SCOPE = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id',
             'workspace_binding_id', 'adapter_id', 'candidate_ref')

    def review(self, selection):
        selection = deepcopy(selection)
        if selection.get('create_agent') or not selection.get('binding_id') or selection.get('provider_home'):
            raise ConnectionError('REMOTE_BINDING_REQUIRED', 'Select an existing agent and binding; remote host setup remains with its Connector.')
        me = self.api('GET', '/connections/me')
        binding = self.api('GET', '/connections/bindings/' + quote(selection['binding_id'], safe=''))
        clients = {adapter: client for client, adapter in CLIENTS.items()}
        client = clients.get(binding['adapter_id'])
        if (not client or binding['agent_id'] != selection['agent'] or binding['server_id'] != me['server_id'] or
                selection.get('client') not in (None, client) or
                selection.get('workspace_id') not in (None, binding['workspace_id']) or
                selection.get('candidate_ref') not in (None, binding['candidate_ref'])):
            raise ConnectionError('PROFILE_CONFLICT', 'The selected binding does not match the requested identity, workspace or harness.')
        selection['client'] = client
        document = dict(format=1, state='done', server_id=me['server_id'], selection=selection,
            remote_scope={key: binding[key] for key in self.SCOPE},
            result=dict(saved=True, agent_id=selection['agent'], binding=binding))
        result = self.observe(document)
        self.save(document)
        return result

    def observe(self, document):
        me = self.api('GET', '/connections/me')
        if me['server_id'] != document['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The saved project belongs to another Server installation.')
        binding = self.api('GET', '/connections/bindings/' + quote(document['remote_scope']['binding_id'], safe=''))
        if any(binding[key] != document['remote_scope'][key] for key in self.SCOPE):
            raise ConnectionError('PROFILE_DRIFT', 'The approved remote binding changed scope. Review its current selection explicitly.')
        if binding['state'] != 'APPROVED':
            raise ConnectionError('CONNECTION_UNAVAILABLE', 'The canonical connection is ' + binding['state'] + '; inspect its current authorization.')
        result = dict(state='configured', server_id=me['server_id'], agent_id=binding['agent_id'],
            binding_id=binding['binding_id'], workspace_id=binding['workspace_id'],
            configuration=self.current(binding['agent_id'], binding['binding_id']),
            topology='remote_operator', execution_location='remote', session_state='not_checked', work_state='not_submitted')
        public = document.get('result', {}).get('public_connection') or document['selection'].get('public_connection')
        if public is not None:
            result['public_connection'] = self._observe_public_id(public['connect_id'],
                workspace_id=binding['workspace_id'], binding_id=binding['binding_id'], server_id=me['server_id'])
        return result
