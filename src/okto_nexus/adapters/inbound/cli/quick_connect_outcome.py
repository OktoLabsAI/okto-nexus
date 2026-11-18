"""Additive versioned output; exit status never substitutes for canonical proof."""
import os

from ....domain.quick_connect import (
    CanonicalConnectionReference, CwdResolution, NameDiscovery, QuickConnectOutcome,
)


def public_wire(value):
    """Preserve unknown legacy shortcut members on disk without echoing them."""
    if not value.get('selection', {}).get('quick_connect'):
        return value
    keys = ('format', 'kind', 'state', 'server_id', 'review_revision', 'selection', 'request',
        'version_check_required', 'effects', 'identity_creation', 'preset_review', 'quick_connect',
        'canonical_metadata_revalidation_requested', 'effects_started', 'lifecycle_requested', 'interaction')
    result = {key: value[key] for key in keys if key in value}
    allowed = ('agent', 'client', 'project', 'label', 'workspace_id', 'binding_id', 'candidate_ref',
        'provider_home', 'create_agent', 'display_name', 'quick_connect', 'public_connection', 'operator_profile')
    result['selection'] = {key: value['selection'][key] for key in allowed if key in value['selection']}
    return result


def annotate(value, document, *, profile, home, plan=False, operation=None):
    selection = (document or {}).get('selection', {})
    metadata = selection.get('quick_connect')
    if metadata is None:
        return value
    public = value.get('public_connection')
    proposal = selection.get('public_connection') or {}
    connected = value.get('state') == 'configured' and public and public.get('state') == 'bound' and not plan
    partial = value.get('state') == 'configured_shortcut_pending' and public and public.get('state') == 'bound'
    if connected or partial:
        reference = public.get('canonical_ref') or {}
        expected = dict(server_id=(document or {}).get('server_id'), agent_id=selection.get('agent'),
            workspace_id=selection.get('workspace_id'), binding_id=selection.get('binding_id'))
        if (proposal.get('connect_id') not in (None, public.get('connect_id'))
                or any(value is not None and reference.get(key) != value for key, value in expected.items())):
            raise ValueError('The public Harness ID does not match the reviewed canonical connection.')
    state = value.get('state', '')
    status = ('cancelled' if state in ('canceled', 'cancelled') else
        'conflict' if state == 'conflict' or value.get('code') in ('HARNESS_ID_ALREADY_EXISTS', 'CONNECTION_SELECTOR_CONFLICT') else
        'unknown' if state in ('unconfirmed', 'outcome_unknown', 'unknown') or value.get('possible_effect') is True else
        'failed' if state in ('failed', 'refused', 'test_failed') else 'pending')
    argv = ['okto-nexus', 'connect']
    if selection.get('client'):
        argv.append(selection['client'])
        if selection.get('label'):
            argv.append(selection['label'])
    if proposal.get('connect_id') or public:
        argv.extend(('--id', (public or proposal)['connect_id']))
    argv.extend(('--home', str(home), '--profile', profile))
    remote = value.get('execution_location') == 'remote' or value.get('topology') == 'remote_operator'
    if not remote and selection.get('project'):
        argv.extend(('--project', selection['project']))
    if remote and selection.get('operator_profile'):
        argv.extend(('--operator-profile', selection['operator_profile']))
    for flag, key in (('--workspace-id', 'workspace_id'), ('--binding-id', 'binding_id')):
        exact = (public or {}).get('canonical_ref', {}).get(key) or selection.get(key)
        if exact:
            argv.extend((flag, exact))
    outcome = QuickConnectOutcome(
        status='connected' if connected else 'configured_shortcut_pending' if partial else 'planned' if plan else status,
        connect_id=public['connect_id'] if connected or partial else None,
        proposed_connect_id=None if connected or partial else proposal.get('connect_id'),
        connect_id_status='bound' if connected or partial else 'reserved' if (document or {}).get('public_id_reservation') else
            'proposed' if proposal else None,
        operation=(operation or metadata.get('operation', 'created')) if connected or partial else None,
        harness=selection.get('client'), project_name=selection.get('label'),
        project_name_source=metadata.get('project_name_source'),
        name_discovery=NameDiscovery(**metadata['name_discovery']) if metadata.get('name_discovery') else None,
        execution_location='remote' if remote else 'local', project_root=None if remote else selection.get('project'),
        cwd_resolution=CwdResolution(**metadata['cwd_resolution']) if metadata.get('cwd_resolution') else None,
        resume_argv=tuple(argv),
        canonical_reference=CanonicalConnectionReference(**public['canonical_ref']) if connected or partial else None)
    return dict(value, quick_connect=outcome.to_dict())


def display_public(value):
    """Render only safe public identity; profile remains advanced JSON metadata."""
    summary = value.get('quick_connect')
    if not summary:
        return False
    if summary['status'] == 'connected':
        operation = summary['operation']
        label = 'Conexão reutilizada' if operation == 'reused' else 'Conexão configurada'
        print(f"{label} — ID do Harness: {summary['connect_id']}")
        print(f"Project: {summary.get('project_name')} | Harness: {summary.get('harness')}")
        print(f"Execution folder: {summary.get('project_root')} | Project name source: {summary.get('project_name_source')}")
        print('Session readiness: not checked. No project work submitted.')
        from .quick_connect_render import public_resume_argv, render_resume_command
        shell = 'powershell' if os.name == 'nt' else 'posix'
        try:
            argv = public_resume_argv(summary['resume_argv'], execution_location=summary['execution_location'])
            command = render_resume_command(argv, shell=shell)
        except ValueError:
            print('Exact public resume command unavailable. Use the retained technical JSON resume_argv.')
        else:
            label = 'PowerShell 7.3+' if shell == 'powershell' else 'POSIX sh'
            print(f'Resume command ({label}): {command}')
        return True
    if summary['status'] == 'configured_shortcut_pending':
        print(f"Conexão configurada — ID do Harness: {summary['connect_id']}")
        print('Local shortcut repair is pending. Resume the same retained intent; no new connection test is needed.')
        return True
    return False
