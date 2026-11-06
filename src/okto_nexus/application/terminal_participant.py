"""Reviewed participant setup: distinct Server, vault and file checkpoints."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from nexus_connector_core.participant_config import ParticipantClientConfig, participant_client_config

from .terminal_connection import ConnectionError, document_revision
from ..adapters.outbound.participant_client import ParticipantHTTP, ParticipantVault
from ..adapters.outbound import participant_files


class TerminalParticipant:
    def __init__(self, home, profile, save):
        self.home, self.profile, self.save = home, profile, save

    def validate(self, saved):
        def require(condition):
            if not condition:
                raise ValueError()
        try:
            review = saved['review']
            require(saved['revision'] == 1 and saved['mode'] == 'participant')
            require(saved['review_revision'] == document_revision(review))
            require(saved['state'] in ('review', 'credential_pending', 'credential_stored', 'file_pending', 'done'))
            selection = review['selection']
            config = ParticipantClientConfig(**review['configuration'])
            require(review['origin'] == selection['server'] == config.approved_origin)
            require(review['context']['agent_id'] == selection['agent'])
            require(review['context']['workspace']['workspace_id'] == selection['workspace_id'])
            require(config.client == selection['client'] and config.entry_name == selection['entry_name'])
            require(config.client_version == selection['client_version'])
            require((review['file'] is None) == (config.client == 'generic'))
            if review['file']:
                require(review['file']['path'] == selection['config_file'])
            if saved['state'] != 'review':
                require(saved['approval'] == saved['review_revision'])
            return review, config
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('PARTICIPANT_PROFILE_INVALID', 'The saved participant review is invalid. Preserve it for inspection; do not apply it.') from None

    def vault(self, review):
        return ParticipantVault(self.home, self.profile, review)

    def key(self, saved, supplied):
        if supplied is not None:
            return supplied
        review, _ = self.validate(saved)
        if saved['state'] == 'review':
            raise ConnectionError('PARTICIPANT_KEY_REQUIRED', 'Supply the existing participant key again; a review never stores credentials.')
        return self.vault(review).call('load')

    def review(self, selection, key):
        context = ParticipantHTTP(selection['server'], key, selection['agent']).context(selection['workspace_id'])
        run_id = uuid4().hex
        environment = 'NEXUS_PARTICIPANT_TOKEN_' + document_revision([
            str(Path(self.home).resolve()), self.profile, run_id])[:32].upper()
        config = participant_client_config(client=selection['client'], client_version=selection['client_version'],
            server_url=selection['server'] + '/mcp', approved_origin=selection['server'],
            entry_name=selection['entry_name'], credential_environment=environment,
            file_scope='manual' if selection['client'] == 'generic' else 'selected' if selection['selected_file'] else 'project',
            loopback_reachable=True)
        file = participant_files.file_plan(selection['config_file'], config) if selection['config_file'] else None
        selection = dict(selection)
        if file:
            selection['config_file'] = file['path']
        review = dict(setup_run_id=run_id, origin=selection['server'], selection=selection,
            context=context, configuration=config.to_dict(), file=file,
            effects=['Store the existing agent key in the OS vault for this setup.',
                     'Apply only the selected MCP entry and keep a protected backup.' if file else
                     'Export reference-only instructions for manual configuration.'])
        saved = dict(revision=1, mode='participant', state='review', review=review,
            review_revision=document_revision(review))
        self.save(saved)
        return saved

    def apply(self, saved, key, approval):
        review, config = self.validate(saved)
        if approval != saved['review_revision']:
            raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact participant review revision before storing credentials or editing configuration.')
        current = ParticipantHTTP(review['origin'], key, review['context']['agent_id']).context(
            review['context']['workspace']['workspace_id'])
        if current['server_id'] != review['context']['server_id']:
            raise ConnectionError('SERVER_CHANGED', 'The Server identity changed. Preserve this setup and inspect the selected origin.')
        if saved['state'] == 'done':
            if review['file']:
                participant_files.current_owned_entry(review['file'], config)
            return self.result(saved, current)
        if current['review_revision'] != review['context']['review_revision']:
            raise ConnectionError('PARTICIPANT_CONTEXT_CHANGED', 'Identity, workspace or policy changed after review. Refresh an unapproved review; preserve an approved setup for inspection.')
        saved = deepcopy(saved)
        if review['file']:
            participant_files.inspect_file(review['file'], config)
        if saved['state'] == 'review':
            saved.update(state='credential_pending', approval=approval)
            self.save(saved)  # Intent precedes the separate vault effect.
        if saved['state'] == 'credential_pending':
            self.vault(review).call('store', key)
            saved['state'] = 'credential_stored'
            self.save(saved)
        if saved['state'] == 'credential_stored':
            saved['state'] = 'file_pending'
            self.save(saved)  # Retain enough evidence to inspect a lost write reply.
        if saved['state'] == 'file_pending':
            result = participant_files.apply_file(review['file'], config) if review['file'] else None
            saved.update(state='done', file_result=result)
            self.save(saved)
        return self.result(saved, current)

    def result(self, saved, context=None):
        review, config = self.validate(saved)
        complete = saved['state'] == 'done'
        return dict(mode='participant', profile=self.profile, setup_run_id=review['setup_run_id'],
            state=('configuration_applied' if review['file'] else 'manual_configuration_required') if complete else saved['state'],
            review_revision=saved['review_revision'], origin=review['origin'],
            context=context or review['context'], project=review['selection']['project'],
            file=review['file'], entry_name=config.entry_name, entry=config.entry(), effects=review['effects'],
            file_result=saved.get('file_result'),
            proof=dict(identity='PASS' if context else 'UNKNOWN',
                client_entry='PASS' if complete and review['file'] else 'UNKNOWN',
                credential_in_client='UNKNOWN', client_reload='UNKNOWN', mcp='UNKNOWN', work='NOT_SUBMITTED'),
            next_action='Use participant launch with this profile to review protected credential delivery to a new terminal client. The client still needs project trust/reload and MCP verification. Vault storage alone does not make it ready.')
