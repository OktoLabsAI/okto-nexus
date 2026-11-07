"""Pure binding rules from the installed Herdr 0.9.5/protocol22 contract.

The base IDs/PIDs/status shape below was captured from the explicitly synthetic
native fixture. It is not evidence of any actual AI provider or personal session.
Display/private fields added by tests are sentinel strings, never captured data.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json

import pytest

from okto_nexus.domain.herdr_observations import (
    HerdrObservationError, WindowsProcessIdentity, bind_agent, binding_from_dict,
    binding_to_dict, normalize_agent_list, normalize_process_info, normalize_snapshot,
    observation_from_dict, preview_hash, reconcile_binding, validate_runtime,
)


def agent(**extra):
    return dict(workspace_id='w1', tab_id='w1:t1', pane_id='w1:p1', terminal_id='term_65fa5400f80f51',
                agent_status='idle', revision=0, agent_session=None, focused=True,
                state_change_seq=1, completion_seq=None, **extra)


def snapshot(row=None):
    row = agent() if row is None else row
    # Non-identity arrays are intentionally empty in this sanitized fixture.
    return dict(version='0.9.5', protocol=22, agents=[row], panes=[deepcopy(row)],
                workspaces=[], tabs=[], layouts=[])


def process_info():
    return dict(pane_id='w1:p1', shell_pid=51412, foreground_process_group_id=46324,
                foreground_processes=[dict(pid=46324)])


IDENTITY = WindowsProcessIdentity('1' * 64, 46324, 134384870609652051, r'C:\synthetic-fixture\codex.exe')


def binding(row=None, *, namespace='installation-a', session='session-a', identity=IDENTITY, info=None):
    return bind_agent(namespace=namespace, session=session, agent=agent() if row is None else row,
                      process_info=process_info() if info is None else info,
                      identity=identity, approved_image=identity.image_path)


def observe(bound, row, previous=None, *, identity=IDENTITY, info=None):
    return reconcile_binding(bound, agent=row, process_info=process_info() if info is None else info,
                             identity=identity, previous=previous)


def test_real_schema_shape_sanitizes_all_display_and_process_text():
    row = agent(name='PRIVATE', title='PRIVATE', terminal_title='PRIVATE', cwd='PRIVATE', foreground_cwd='PRIVATE',
                state_labels={'prompt': 'PRIVATE'}, tokens={'prompt': 'PRIVATE'})
    clean = normalize_snapshot(snapshot(row))
    info = process_info()
    info['tty'] = 'PRIVATE'
    info['foreground_processes'][0].update(argv=['PRIVATE'], cmdline='PRIVATE', name='PRIVATE', cwd='PRIVATE')
    clean_info = normalize_process_info(info)
    assert 'PRIVATE' not in json.dumps([clean, clean_info])
    assert clean['agents'][0]['terminal_id'] == row['terminal_id']
    assert clean_info == process_info()
    bound = binding(clean['agents'][0], info=clean_info)
    assert observe(bound, clean['agents'][0]).state == 'idle'


@pytest.mark.parametrize('version,protocol', [('0.9.4', 22), ('0.9.5', 21), ('0.9.5', True), ('0.9.5', '22'), (None, 22)])
def test_incompatible_contract_fails_closed(version, protocol):
    with pytest.raises(HerdrObservationError, match='HERDR_UNSUPPORTED_CONTRACT'):
        validate_runtime(version, protocol)


@pytest.mark.parametrize('field,value', [
    ('revision', True), ('revision', -1), ('revision', 1 << 64), ('state_change_seq', 1.5),
    ('completion_seq', '1'), ('agent_status', 'finished'), ('focused', 1),
    ('terminal_id', ''), ('pane_id', ['w1:p1']), ('agent_session', {'kind': 'id'}),
])
def test_malformed_agent_metadata_is_sanitized_unavailability(field, value):
    row = agent()
    row[field] = value
    with pytest.raises(HerdrObservationError) as error:
        normalize_agent_list([row])
    assert 'PRIVATE' not in str(error.value)


def test_duplicate_or_inconsistent_snapshot_is_not_partial_acceptance():
    raw = snapshot()
    raw['agents'].append(deepcopy(raw['agents'][0]))
    with pytest.raises(HerdrObservationError, match='HERDR_AMBIGUOUS_IDENTITY'):
        normalize_snapshot(raw)
    raw = snapshot()
    raw['panes'][0]['terminal_id'] = 'another-terminal'
    with pytest.raises(HerdrObservationError, match='HERDR_INCONSISTENT_SNAPSHOT'):
        normalize_snapshot(raw)


def test_explicit_namespace_session_host_and_birth_are_all_binding_identity():
    first = binding()
    assert binding_from_dict(binding_to_dict(first)) == first
    assert binding(namespace='installation-b') != first
    assert binding(session='session-b') != first
    assert binding(identity=replace(IDENTITY, host_id='2' * 64)) != first
    assert binding(identity=replace(IDENTITY, creation_filetime=IDENTITY.creation_filetime + 1)) != first
    assert len({preview_hash(item) for item in [first, binding(namespace='installation-b'), binding(session='session-b')]}) == 3
    with pytest.raises(FrozenInstanceError):
        first.pid = 1


def test_rename_alias_and_directory_do_not_reassign_identity():
    bound = binding()
    renamed = agent(name='renamed', title='renamed', cwd='other-directory', display_agent='untrusted-label')
    assert binding(renamed) == bound
    assert observe(bound, renamed).binding_hash == preview_hash(bound)


@pytest.mark.parametrize('field', ['workspace_id', 'tab_id', 'pane_id', 'terminal_id'])
def test_move_or_changed_location_requires_rebinding(field):
    bound = binding()
    moved = agent()
    moved[field] = 'changed'
    info = process_info()
    if field == 'pane_id':
        info['pane_id'] = 'changed'
    with pytest.raises(HerdrObservationError, match='HERDR_BINDING_CHANGED'):
        observe(bound, moved, info=info)


def test_removal_and_pid_reuse_do_not_transfer_binding():
    bound = binding()
    with pytest.raises(HerdrObservationError, match='HERDR_BOUND_OCCUPANT_MISSING'):
        observe(bound, None)
    with pytest.raises(HerdrObservationError, match='HERDR_BINDING_CHANGED'):
        observe(bound, agent(), identity=replace(IDENTITY, creation_filetime=IDENTITY.creation_filetime + 1))


@pytest.mark.parametrize('edit', ['shell', 'multiple', 'no_shell', 'no_group', 'wrong_group', 'wrong_pane', 'empty'])
def test_process_selection_requires_native_non_shell_coherent_candidate(edit):
    info = process_info()
    if edit == 'shell':
        info['shell_pid'] = IDENTITY.pid
    elif edit == 'multiple':
        info['foreground_processes'].append({'pid': 456})
    elif edit == 'no_shell':
        info['shell_pid'] = None
    elif edit == 'no_group':
        info['foreground_process_group_id'] = None
    elif edit == 'wrong_group':
        info['foreground_process_group_id'] = 456
    elif edit == 'wrong_pane':
        info['pane_id'] = 'different-pane'
    else:
        info['foreground_processes'] = []
    with pytest.raises(HerdrObservationError, match='HERDR_OCCUPANT_UNPROVEN'):
        binding(info=info)


@pytest.mark.parametrize('name', ['node.exe', 'cmd.exe', 'pwsh.exe', 'bash.exe', 'python.exe', 'python3.13.exe', 'java.exe', 'dotnet.exe', 'wsl.exe'])
def test_interpreter_shell_and_runtime_wrappers_are_not_occupant_proof(name):
    identity = replace(IDENTITY, image_path='C:\\synthetic-fixture\\' + name)
    with pytest.raises(HerdrObservationError, match='HERDR_WRAPPER_UNSUPPORTED'):
        binding(identity=identity)


def test_image_approval_is_exact_and_local():
    with pytest.raises(HerdrObservationError, match='HERDR_PROCESS_IMAGE_CHANGED'):
        bind_agent(namespace='a', session='b', agent=agent(), process_info=process_info(),
                   identity=IDENTITY, approved_image=r'C:\another\codex.exe')
    with pytest.raises(HerdrObservationError, match='HERDR_LOCAL_IMAGE_REQUIRED'):
        replace(IDENTITY, image_path=r'\\remote\share\codex.exe')
    with pytest.raises(HerdrObservationError, match='HERDR_LOCAL_IMAGE_REQUIRED'):
        replace(IDENTITY, image_path='codex.exe')
    assert binding(identity=replace(IDENTITY, image_path=r'C:\SYNTHETIC-FIXTURE\CODEX.EXE')) == binding()


def test_optional_session_id_is_supplemental_and_path_is_never_identity():
    row = agent()
    row['agent_session'] = dict(source='hook', agent='synthetic', kind='id', value='opaque-reference')
    bound = binding(row)
    assert bound.agent_session_id_hash is not None
    assert 'opaque-reference' not in json.dumps(binding_to_dict(bound))
    changed = deepcopy(row)
    changed['agent_session']['value'] = 'different-reference'
    with pytest.raises(HerdrObservationError, match='HERDR_BINDING_CHANGED'):
        observe(bound, changed)
    row['agent_session'] = dict(source='hook', agent='synthetic', kind='path', value='PRIVATE-PATH')
    clean = normalize_agent_list([row])[0]
    assert clean['agent_session'] is None and 'PRIVATE-PATH' not in json.dumps(clean)
    assert binding(clean).agent_session_id_hash is None
    info = process_info()
    info['shell_pid'] = IDENTITY.pid
    with pytest.raises(HerdrObservationError, match='HERDR_OCCUPANT_UNPROVEN'):
        binding(row, info=info)


@pytest.mark.parametrize('completion', [None, 0, 10])
def test_initial_done_is_idle_without_new_completion(completion):
    row = agent()
    row.update(agent_status='done', state_change_seq=10, completion_seq=completion)
    observed = observe(binding(row), row)
    assert observed.state == 'idle' and observed.evidence == 'inferred' and observed.completion_ref is None


def test_completion_requires_new_coherent_counter_and_remains_stable_until_omitted():
    row, bound = agent(), binding()
    initial = observe(bound, row)
    row.update(agent_status='working', revision=1, state_change_seq=2)
    working = observe(bound, row, initial)
    row.update(agent_status='done', revision=2, state_change_seq=3, completion_seq=3)
    completed = observe(bound, row, working)
    assert completed.completion_ref == 'herdr:' + preview_hash(bound)[7:] + ':3'
    assert observation_from_dict(completed.to_dict()) == completed
    row['agent_status'] = 'idle'
    repeated = observe(bound, row, completed)
    assert repeated.completion_ref == completed.completion_ref
    row['completion_seq'] = None
    omitted = observe(bound, row, repeated)
    assert omitted.completion_ref is None and omitted.last_completion_seq == 3
    row['completion_seq'] = 3
    assert observe(bound, row, omitted).completion_ref is None


@pytest.mark.parametrize('status,state_seq,completion', [('working', 2, 2), ('blocked', 2, 2), ('idle', 3, 2), ('done', 2, None)])
def test_incoherent_or_missing_completion_counter_never_emits_ref(status, state_seq, completion):
    row, bound = agent(), binding()
    previous = observe(bound, row)
    row.update(agent_status=status, revision=1, state_change_seq=state_seq, completion_seq=completion)
    assert observe(bound, row, previous).completion_ref is None


@pytest.mark.parametrize('field', ['revision', 'state_change_seq', 'completion_seq'])
def test_counter_regression_requires_rebinding(field):
    row, bound = agent(), binding()
    row.update(revision=10, state_change_seq=10, completion_seq=10)
    previous = observe(bound, row)
    row[field] = 9
    with pytest.raises(HerdrObservationError, match='HERDR_COUNTER_REGRESSED'):
        observe(bound, row, previous)


def test_same_positive_state_sequence_cannot_change_normalized_state():
    row, bound = agent(), binding()
    previous = observe(bound, row)
    row['agent_status'] = 'blocked'
    with pytest.raises(HerdrObservationError, match='HERDR_INCONSISTENT_STATE_SEQUENCE'):
        observe(bound, row, previous)


def test_herdr_uint64_counters_are_not_cast_to_nexus_signed_sequence():
    row, bound = agent(), binding()
    row.update(revision=(1 << 64) - 2, state_change_seq=(1 << 64) - 2)
    previous = observe(bound, row)
    row.update(revision=(1 << 64) - 1, state_change_seq=(1 << 64) - 1, completion_seq=(1 << 64) - 1)
    final = observe(bound, row, previous)
    assert final.completion_ref.endswith(':18446744073709551615')


def test_corrupt_checkpoint_cannot_inject_completion_or_identity():
    bound, row = binding(), agent()
    saved = observe(bound, row).to_dict()
    saved['completion_ref'] = 'PRIVATE-MALICIOUS-REF'
    with pytest.raises(HerdrObservationError, match='HERDR_MALFORMED_CHECKPOINT'):
        observation_from_dict(saved)
    saved = binding_to_dict(bound)
    saved['unrecognized'] = 'PRIVATE'
    with pytest.raises(HerdrObservationError, match='HERDR_MALFORMED_BINDING'):
        binding_from_dict(saved)
