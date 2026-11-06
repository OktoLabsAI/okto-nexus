"""Reviewed foreground launch with a durable intent before the process effect."""
from copy import deepcopy
from uuid import uuid4

from .terminal_connection import ConnectionError, document_revision
from .terminal_participant import TerminalParticipant
from ..adapters.outbound.participant_client import ParticipantHTTP
from ..adapters.outbound import participant_process


class ParticipantLaunch:
    def __init__(self, home, profile, save):
        self.home, self.profile, self.save = home, profile, save
        self.setup = TerminalParticipant(home, profile, lambda _: None)

    def _setup(self, saved):
        review, config = self.setup.validate(saved)
        if saved['state'] != 'done':
            raise ConnectionError('PARTICIPANT_SETUP_INCOMPLETE', 'Complete the retained participant init before launching its client.')
        if config.client == 'generic':
            raise ConnectionError('PARTICIPANT_LAUNCH_UNSUPPORTED', 'Generic clients require their own secure launcher.')
        return review, config

    def _authenticate(self, saved, review):
        key = self.setup.key(saved, None)
        context = ParticipantHTTP(review['origin'], key, review['context']['agent_id']).context(
            review['context']['workspace']['workspace_id'])
        if context['server_id'] != review['context']['server_id']:
            raise ConnectionError('SERVER_CHANGED', 'The selected Server identity changed. Inspect the retained profile.')
        return key, context

    def review(self, saved, executable, *, environment, previous=None):
        setup, config = self._setup(saved)
        selected = participant_process.select_executable(config.client, executable, environment=environment)
        process = participant_process.launch_context(setup, config, selected, environment=environment)
        _, context = self._authenticate(saved, setup)
        review = dict(launch_id=uuid4().hex, setup_revision=saved['review_revision'],
            client=config.client, credential_reference=config.credential_environment,
            origin=setup['origin'], context=context, process=process,
            effects=['Read the existing OS vault key and authenticate this participant.',
                'Start the selected client in this terminal with the named credential in its child environment.',
                'The client loads its own settings, MCP servers, plugins and hooks under its existing policies.',
                'No prompt or work is submitted by Nexus. Client login and project trust may still be required.'],
            previous=dict(review_revision=previous['review_revision'], state=previous['state'],
                launch_id=previous['review']['launch_id'], pid_hint=previous.get('pid_hint'),
                exit_code=previous.get('exit_code'), process=previous['review']['process']) if previous else None)
        intent = dict(revision=1, mode='participant_launch', state='review', review=review,
            review_revision=document_revision(review))
        self.save(intent)
        return intent

    def validate(self, intent, saved):
        def require(condition):
            if not condition:
                raise ValueError()
        try:
            review = intent['review']
            require(intent['revision'] == 1 and intent['mode'] == 'participant_launch')
            require(intent['state'] in ('review', 'starting', 'started', 'exited'))
            require(intent['review_revision'] == document_revision(review))
            require(review['setup_revision'] == saved['review_revision'])
            if intent['state'] != 'review':
                require(intent['approval'] == intent['review_revision'])
            return review
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('PARTICIPANT_LAUNCH_INVALID', 'The saved launch intent is invalid or belongs to another setup. Preserve it for inspection.') from None

    def apply(self, intent, saved, approval, *, environment):
        review = self.validate(intent, saved)
        if approval != intent['review_revision']:
            raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact launch review before starting the external client.')
        if intent['state'] != 'review':
            # A lost spawn/checkpoint response never causes automatic relaunch.
            return self.result(intent)
        setup, config = self._setup(saved)
        key, current = self._authenticate(saved, setup)
        if current['review_revision'] != review['context']['review_revision']:
            raise ConnectionError('PARTICIPANT_CONTEXT_CHANGED', 'Participant authority changed after launch review. Create a new launch review.')
        context = participant_process.launch_context(setup, config, review['process']['executable'], environment=environment)
        if context != review['process']:
            raise ConnectionError('CLIENT_LAUNCH_CHANGED', 'The client binary, project, configuration or launch context changed. Review a new launch intent.')
        child_env = participant_process.child_environment(config, key, environment)
        intent = deepcopy(intent)
        intent.update(state='starting', approval=approval)
        self.save(intent)
        try:
            child = participant_process.spawn(context, child_env)
        finally:
            child_env.pop(config.credential_environment, None)
        intent.update(state='started', pid_hint=child.pid, credential_delivery='supplied_to_owned_spawn')
        try:
            self.save(intent)
        except Exception:
            # Keep the owned foreground child attached even if persistence fails.
            # The prior starting checkpoint fences retries; do not kill by PID.
            child.wait()
            raise
        exit_code = child.wait()
        intent.update(state='exited', exit_code=exit_code)
        self.save(intent)
        return self.result(intent)

    def result(self, intent):
        return dict(mode='participant_launch', profile=self.profile, state=intent['state'],
            review_revision=intent['review_revision'], review=intent['review'],
            pid_hint=intent.get('pid_hint'), exit_code=intent.get('exit_code'),
            proof=dict(credential_delivery=intent.get('credential_delivery', 'UNKNOWN'),
                credential_in_client='UNKNOWN', client_reload='UNKNOWN', mcp='UNKNOWN', work='NOT_SUBMITTED'),
            next_action='Client MCP authentication and participation need separate evidence. A PID or exit code is not readiness. '
                'Use --new only to request another launch; an uncertain prior launch may still be running.')
