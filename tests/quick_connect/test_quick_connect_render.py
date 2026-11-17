"""Public resume commands preserve exact context; rendering never executes."""
from copy import deepcopy
import shlex

import pytest

from okto_nexus.adapters.inbound.cli.quick_connect_outcome import display_public
from okto_nexus.adapters.inbound.cli.quick_connect_render import public_resume_argv, render_resume_command
from test_quick_connect_outcome import inputs, outcome


def test_local_public_resume_keeps_home_root_and_full_selectors_without_technical_profile(capsys):
    value, document = inputs()
    before = deepcopy((value, document))
    result = outcome(value, document)
    quick = result['quick_connect']
    wire = quick['resume_argv']
    public = public_resume_argv(wire, execution_location='local')
    assert wire[wire.index('--profile') + 1] == 'opaque-technical-profile'
    assert '--profile' not in public and 'opaque-technical-profile' not in public
    assert public[public.index('--home') + 1] == '/safe home'
    assert public[public.index('--project') + 1] == document['selection']['project']
    for flag, key in (('--workspace-id', 'workspace_id'), ('--binding-id', 'binding_id')):
        assert public[public.index(flag) + 1] == quick['canonical_reference'][key]
    assert (value, document) == before
    assert display_public(result) is True
    printed = capsys.readouterr().out
    assert 'Resume command (' in printed and 'opaque-technical-profile' not in printed


def test_remote_public_resume_keeps_operator_and_exact_refs_without_execution_host_path(capsys):
    value, document = inputs()
    value.update(topology='remote_operator', execution_location='remote')
    document['selection']['operator_profile'] = 'review operator'
    document['selection']['project'] = '/connector/private/execution-root'
    document['selection']['quick_connect']['cwd_resolution'].update(project_root=None, source='remote')
    quick = outcome(value, document)['quick_connect']
    assert quick.get('project_root') is None
    public = public_resume_argv(quick['resume_argv'], execution_location='remote')
    assert '--profile' not in public and '--project' not in public
    assert public[public.index('--operator-profile') + 1] == 'review operator'
    assert public[public.index('--workspace-id') + 1] == 'workspace'
    assert public[public.index('--binding-id') + 1] == 'binding'
    assert '/connector/private/execution-root' not in public
    display_public(outcome(value, document))
    assert '/connector/private/execution-root' not in capsys.readouterr().out


def test_remote_missing_operator_does_not_print_a_command_that_could_select_local_service(capsys):
    value, document = inputs()
    value.update(topology='remote_operator', execution_location='remote')
    document['selection']['quick_connect']['cwd_resolution'].update(project_root=None, source='remote')
    result = outcome(value, document)
    display_public(result)
    printed = capsys.readouterr().out
    assert 'Exact public resume command unavailable' in printed
    assert 'Resume command (' not in printed
    assert '--profile' in result['quick_connect']['resume_argv']


def test_pending_shortcut_never_removes_the_same_technical_recovery_intent(capsys):
    value, document = inputs()
    value['state'] = 'configured_shortcut_pending'
    result = outcome(value, document)
    display_public(result)
    assert '--profile' in result['quick_connect']['resume_argv']
    assert 'Resume command (' not in capsys.readouterr().out


@pytest.mark.parametrize('values', [
    ['okto-nexus', 'connect', 'claude', "Unicode Ω 'quoted' & $(touch MARKER) `id`", '--id', 'reviewer'],
    ['program path', '', '"double"', 'back\\slash\\', '; echo MARKER', '$HOME', 'a\tb'],
])
def test_posix_render_roundtrips_arguments_without_side_effects(values, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Rendering must not invoke a shell or inspect the filesystem')
    monkeypatch.setattr('subprocess.run', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('builtins.open', forbidden)
    assert shlex.split(render_resume_command(values, shell='posix')) == values
    powershell = render_resume_command(values, shell='powershell')
    assert "$PSVersionTable.PSVersion -lt [version]'7.3'" in powershell
    assert "$PSNativeCommandArgumentPassing = 'Standard'" in powershell


@pytest.mark.parametrize('value', ['line\nbreak', 'line\rbreak', 'nul\x00byte'])
@pytest.mark.parametrize('shell', ['posix', 'powershell'])
def test_unpasteable_control_arguments_are_refused(value, shell):
    with pytest.raises(ValueError):
        render_resume_command(['okto-nexus', value], shell=shell)


def test_cmd_is_not_misrepresented_as_powershell_or_posix():
    with pytest.raises(ValueError):
        render_resume_command(['okto-nexus'], shell='cmd')


@pytest.mark.parametrize('label', ['--profile', '--home', '--binding-id'])
def test_option_like_project_names_are_data_not_selector_names(label):
    value, document = inputs()
    document['selection']['label'] = label
    quick = outcome(value, document)['quick_connect']
    public = public_resume_argv(quick['resume_argv'], execution_location='local')
    assert quick['resume_argv'][3] == label
    assert public[:3] == ('okto-nexus', 'connect', 'claude')
    assert public[public.index('--home') + 1] == '/safe home'
    assert '--profile' not in public and 'opaque-technical-profile' not in public


def test_option_like_selector_values_keep_their_arity_and_parse_as_values():
    from okto_nexus.adapters.inbound.cli.connect_arguments import parse_connect_args
    from okto_nexus.adapters.inbound.cli.quick_connect_outcome import annotate
    value, document = inputs()
    document['selection']['project'] = '--home'
    document['selection']['quick_connect']['cwd_resolution']['project_root'] = '--home'
    quick = annotate(value, document, profile='--binding-id', home='/safe home')['quick_connect']
    public = public_resume_argv(quick['resume_argv'], execution_location='local')
    assert '--project=--home' in public
    args, service = parse_connect_args(list(public[2:]))
    assert str(args.project) == '--home' and args.workspace_id == 'workspace' and args.binding_id == 'binding'
    assert args.profile is None and service == ['--home', '/safe home']
