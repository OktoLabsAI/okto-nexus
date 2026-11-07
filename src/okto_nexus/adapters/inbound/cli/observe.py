"""Optional external observation; no Server startup, Connector or execution."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from ....application.herdr_observer import (
    HerdrObserver, ObserverError, ObserverPersistenceError, new_document, sample_source, selection_hash, validate_document,
)
from ....domain.herdr_observations import HerdrObservationError, binding_from_dict
from ....observation_client import ObservationClient, ObservationClientError
from ...outbound.observation.herdr import HerdrCLI, HerdrTransportError
from ...outbound.observation.journal import ObservationJournal, ObservationJournalError
from ...outbound.observation.windows_identity import open_process_identity


def _emit(value):
    print(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False), flush=True)


def _parser():
    parser = argparse.ArgumentParser(prog='okto-nexus observe', description=__doc__, allow_abbrev=False)
    sources = parser.add_subparsers(dest='source', required=True)
    herdr = sources.add_parser('herdr', allow_abbrev=False,
        help='Read an explicitly associated local Windows Herdr 0.9.5 process.')
    actions = herdr.add_subparsers(dest='action', required=True)
    bind = actions.add_parser('bind', allow_abbrev=False,
        help='Preview a binding; repeat with --approve-selection to save it without publishing.')
    bind.add_argument('--state', required=True, help='New local journal path; parent directory must exist.')
    bind.add_argument('--herdr-executable', required=True, help='Absolute path to the approved Herdr executable.')
    bind.add_argument('--session', required=True, help='Explicit local Herdr session, including default if intended.')
    bind.add_argument('--namespace', required=True, help='Stable unique installation namespace chosen for this binding.')
    bind.add_argument('--pane', required=True, help='Exact pane ID; aliases and focused-pane defaults are not accepted.')
    bind.add_argument('--server', required=True, help='Nexus HTTPS origin, or loopback HTTP origin.')
    bind.add_argument('--source-id', required=True)
    bind.add_argument('--instance-id', required=True)
    bind.add_argument('--generation', type=int, required=True, help='Generation already approved by Nexus management.')
    bind.add_argument('--interval', type=int, default=15, help='Polling interval, 5..300 seconds (default: 15).')
    bind.add_argument('--ttl', type=int, default=90, help='Report TTL, 30..3600 seconds and at least twice interval.')
    bind.add_argument('--approve-selection', help='Exact sha256 selection shown by the preview.')
    run = actions.add_parser('run', allow_abbrev=False,
        help='Publish fresh metadata with a restricted observation token; Ctrl+C stops observation.')
    run.add_argument('--state', required=True)
    run.add_argument('--token-env', required=True, help='Name of the environment variable containing the nxobs_ token.')
    run.add_argument('--once', action='store_true', help='Publish one report (historical with --retry-pending), then exit.')
    recovery = run.add_mutually_exclusive_group()
    recovery.add_argument('--retry-pending', action='store_true', help='First resend the exact saved report after a prior failure.')
    recovery.add_argument('--discard-refused', action='store_true', help='Discard a known non-admitted report, preserving its sequence.')
    status = actions.add_parser('status', allow_abbrev=False, help='Read local binding/checkpoint metadata without publishing.')
    status.add_argument('--state', required=True)
    return parser


def _bind(args):
    source = HerdrCLI(args.herdr_executable, args.session)
    contract = source.contract()
    binding, observation, _ = sample_source(source, open_process_identity, pane=args.pane,
        namespace=args.namespace, session=args.session)
    document = new_document(executable=args.herdr_executable, binding=binding, observation=observation,
        server_origin=args.server, source_id=args.source_id, observed_instance_id=args.instance_id,
        generation=args.generation, interval_seconds=args.interval, valid_for_seconds=args.ttl)
    selection = selection_hash(document)
    if args.approve_selection is None:
        _emit(dict(status='preview', selection=selection, contract=contract, binding=document['binding'],
            server_origin=document['server_origin'], source_id=args.source_id,
            observed_instance_id=args.instance_id, generation=args.generation,
            interval_seconds=args.interval, valid_for_seconds=args.ttl,
            activity=observation.state, evidence=observation.evidence))
        return 0
    if args.approve_selection != selection:
        raise ObserverError('OBSERVER_SELECTION_CHANGED')
    with ObservationJournal(Path(args.state).absolute()) as journal:
        journal.create(document)
    _emit(dict(status='bound', selection=selection, source_id=args.source_id,
               observed_instance_id=args.instance_id, generation=args.generation))
    return 0


def _token(variable):
    # A secret-bearing variable must never overlap the child's necessary OS
    # environment (e.g. TEMP/APPDATA), even if the caller selected such a name.
    reserved = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'USERPROFILE',
        'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'HOME', 'HOMEDRIVE', 'HOMEPATH',
        'PROGRAMDATA', 'LANG', 'LC_ALL', 'NO_COLOR', 'OS', 'PROCESSOR_ARCHITECTURE',
        'NUMBER_OF_PROCESSORS'}
    if (not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', variable)
            or variable.upper() in reserved or variable.upper().startswith(('HERDR_', 'XDG_'))):
        raise ObserverError('OBSERVER_TOKEN_ENV_INVALID')
    value = os.environ.get(variable)
    if value is None:
        raise ObserverError('OBSERVER_TOKEN_REQUIRED')
    return value


def _run(args):
    token = _token(args.token_env)
    with ObservationJournal(Path(args.state).absolute()) as journal:
        document = journal.read()
        if document is None:
            raise ObserverError('OBSERVER_BINDING_REQUIRED')
        document = validate_document(document)
        binding = binding_from_dict(document['binding'])
        # Validate the restricted token before invoking any external executable.
        publisher = ObservationClient(document['server_origin'], token=token)
        recovery = HerdrObserver(source=None, open_identity=open_process_identity,
                                 journal=journal, publisher=publisher)
        recovered = recovery.resolve_pending(retry=args.retry_pending, discard_refused=args.discard_refused)
        if recovered is not None:
            _emit(dict(status='historical_receipt', receipt=recovered))
            if args.once:
                return 0
        source = HerdrCLI(document['herdr_executable'], binding.session)
        observer = HerdrObserver(source=source, open_identity=open_process_identity,
                                 journal=journal, publisher=publisher)
        source.contract()
        while True:
            receipt = observer.publish_current()
            _emit(dict(status='published', receipt=receipt))
            if args.once:
                return 0
            time.sleep(document['interval_seconds'])


def _status(args):
    with ObservationJournal(Path(args.state).absolute()) as journal:
        document = journal.read()
        if document is None:
            raise ObserverError('OBSERVER_BINDING_REQUIRED')
        document = validate_document(document)
        _emit(dict(status='reassociation_required' if document['invalidated'] else 'bound',
            source_id=document['source_id'], observed_instance_id=document['observed_instance_id'],
            generation=document['generation'], sequence=document['sequence'],
            pending=document['pending'] is not None, pending_failure=document['pending_failure'],
            last_receipt=document['last_receipt']))
    return 0


def run_observe(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.action == 'bind':
            return _bind(args)
        if args.action == 'status':
            return _status(args)
        return _run(args)
    except KeyboardInterrupt:
        _emit(dict(status='stopped', reason='OBSERVER_INTERRUPTED'))
        return 130
    except ObserverPersistenceError as error:
        _emit(dict(status='checkpoint_failed', code=error.code, outcome_unknown=error.outcome_unknown,
            remote_admitted=error.remote_admitted, receipt=error.receipt))
        return 3
    except (ObserverError, HerdrObservationError, HerdrTransportError, ObservationJournalError) as error:
        _emit(dict(status='unavailable', code=error.code))
        return 2
    except ObservationClientError as error:
        _emit(dict(status='publication_failed', code=error.code,
            outcome_unknown=error.outcome_unknown, http_status=error.status,
            retry_after_seconds=error.retry_after_seconds))
        return 3 if error.outcome_unknown else 2
    except (OSError, ValueError):
        # No local paths, child output, remote messages or environment values.
        _emit(dict(status='unavailable', code='OBSERVER_LOCAL_IO_ERROR'))
        return 2


if __name__ == '__main__':
    sys.exit(run_observe())
