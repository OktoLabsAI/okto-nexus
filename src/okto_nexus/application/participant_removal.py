"""Local participant compensation; no Server deletion or distributed transaction."""
from copy import deepcopy
from uuid import uuid4

from .terminal_connection import ConnectionError, document_revision
from .terminal_participant import TerminalParticipant
from ..adapters.outbound import participant_files


class ParticipantRemoval:
    def __init__(self, home, profile, save):
        self.profile, self.save = profile, save
        self.setup = TerminalParticipant(home, profile, save)

    def review(self, saved, *, keep_config=False):
        setup, config = self.setup.validate(saved)
        previous = saved.get('removal')
        if previous and previous['stage'] != 'review':
            raise ConnectionError('PARTICIPANT_REMOVAL_APPROVED',
                'Resume the retained removal checkpoints. An approved removal cannot be replaced by another plan.')
        file = None if keep_config else participant_files.removal_plan(setup['file'], config, setup_state=saved['state'])
        review = dict(removal_id=uuid4().hex, setup_revision=saved['review_revision'], setup_state=saved['state'],
            setup_run_id=setup['setup_run_id'], origin=setup['origin'], agent_id=setup['context']['agent_id'],
            entry_name=config.entry_name, file=file, keep_config=keep_config,
            remove_credential=saved['state'] != 'review',
            effects=['Retire this local profile so init/reconnect/launch cannot restore it.',
                'Remove only its still-owned MCP entry and keep a protected backup.' if file else
                'Leave the client configuration untouched; inspect remaining manual configuration separately.',
                'Remove only this setup\'s isolated OS-vault entry if it may have been stored.',
                'Existing clients may retain the key in memory. Close or reconfigure them explicitly.',
                'Server identity, API key validity, runtime, bindings and grants remain unchanged.'])
        saved = deepcopy(saved)
        saved['removal'] = dict(revision=1, stage='review', review=review, review_revision=document_revision(review))
        self.save(saved)
        return saved

    def apply(self, saved, approval):
        setup, config = self.setup.validate(saved)
        removal = saved.get('removal')
        if not removal or approval != removal['review_revision']:
            raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact local removal review before changing the file or vault.')
        review = removal['review']
        saved = deepcopy(saved)
        removal = saved['removal']
        if removal['stage'] == 'review':
            if saved['state'] != review['setup_state']:
                raise ConnectionError('PARTICIPANT_SETUP_CHANGED', 'Setup advanced after removal review. Refresh the unapproved removal plan.')
            if review['file']:
                participant_files.inspect_file(review['file'], config)
            removal.update(stage='file_pending', approval=approval)
            self.save(saved)  # Retirement and file-effect intent precede effects.
        if removal['stage'] == 'file_pending':
            removal['file_result'] = participant_files.apply_removal(review['file'], config) if review['file'] else None
            removal['stage'] = 'vault_pending'
            self.save(saved)
        if removal['stage'] == 'vault_pending':
            if review['remove_credential']:
                self.setup.vault(setup).call('remove')
            removal['stage'] = 'done'
            self.save(saved)
        return self.result(saved)

    def result(self, saved):
        self.setup.validate(saved)
        removal = saved['removal']
        return dict(mode='participant_removal', profile=self.profile, stage=removal['stage'],
            state='removed' if removal['stage'] == 'done' else 'review' if removal['stage'] == 'review' else 'removal_in_progress',
            review_revision=removal['review_revision'], review=removal['review'],
            file_result=removal.get('file_result'),
            evidence_scope='retained_local_removal_receipt',
            next_action='Resume this removal after uncertainty. Existing clients must be closed/reconfigured separately. '
                'Backups and nonsecret receipts are retained; a new connection requires a new profile and explicit init.')
