from dataclasses import replace
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from nexus_connector_core.user_service_definition import (
    TASK_NAMESPACE, UserServiceDefinition, windows_definition_digest, windows_logon_task,
    windows_with_enabled, windows_enablement_matches,
    windows_with_execution, windows_execution_matches,
)


def definition(**changes):
    base = UserServiceDefinition(component='connector', instance_id='svc_' + 'a' * 64,
        principal='S-1-5-21-100-200-300-1001', executable=r'C:\Program Files\Okto & Co\pythonw.exe',
        arguments=('-m', 'package.foreground', '--context', r'C:\Users\a b\state & work\context.json'),
        working_directory=r'C:\Users\a b\state & work')
    return replace(base, **changes)


def test_user_task_is_literal_foreground_least_privilege_without_stacked_recovery():
    spec = definition()
    xml = windows_logon_task(spec)
    root = ET.fromstring(xml)
    def text(path):
        return root.find(path, {'t': TASK_NAMESPACE}).text
    assert text('t:Actions/t:Exec/t:Command') == spec.executable
    assert text('t:Actions/t:Exec/t:Arguments') == subprocess.list2cmdline(spec.arguments)
    assert text('t:Actions/t:Exec/t:WorkingDirectory') == spec.working_directory
    assert text('t:Principals/t:Principal/t:UserId') == spec.principal
    assert text('t:Triggers/t:LogonTrigger/t:UserId') == spec.principal
    assert text('t:Principals/t:Principal/t:LogonType') == 'InteractiveToken'
    assert text('t:Principals/t:Principal/t:RunLevel') == 'LeastPrivilege'
    assert text('t:Settings/t:MultipleInstancesPolicy') == 'IgnoreNew'
    assert text('t:Settings/t:ExecutionTimeLimit') == 'PT0S'
    assert text('t:Settings/t:AllowHardTerminate') == 'false'
    assert root.find('t:Settings/t:RestartOnFailure', {'t': TASK_NAMESPACE}) is None
    assert 'S4U' not in xml and 'Password' not in xml and 'BootTrigger' not in xml


def test_instance_names_and_revision_identify_exact_configuration():
    base = definition()
    assert base.name != definition(instance_id='svc_' + 'b' * 64).name
    assert base.name != definition(component='server').name
    changed = definition(working_directory=r'D:\Other project')
    assert base.name == changed.name and base.revision_digest != changed.revision_digest
    assert base == definition()


@pytest.mark.parametrize('changes', [
    {'principal': 'user-from-environment'}, {'executable': 'python.exe'},
    {'working_directory': 'relative'}, {'arguments': ('--context', r'%USERPROFILE%\context.json')},
    {'arguments': ('--context', 'line\nnew')}, {'instance_id': 'not-canonical'},
])
def test_ambiguous_or_unresolved_context_is_refused(changes):
    with pytest.raises(ValueError):
        windows_logon_task(definition(**changes))


def test_native_definition_digest_preserves_unknown_edits_and_normalizes_formatting():
    xml = windows_logon_task(definition())
    original = windows_definition_digest(xml)
    assert windows_definition_digest(xml.replace('><', '>\n  <')) == original
    assert windows_definition_digest(xml.replace('LeastPrivilege', 'HighestAvailable')) != original
    assert windows_definition_digest(xml.replace('</Settings>', '<Priority>4</Priority></Settings>')) != original
    with pytest.raises(ValueError):
        windows_definition_digest('<!DOCTYPE Task []>' + xml)


@pytest.mark.skipif(sys.platform != 'win32', reason='Native XML validation requires Windows Task Scheduler')
def test_windows_scheduler_validates_xml_without_registering_or_starting(tmp_path):
    win32com = pytest.importorskip('win32com.client')
    security = pytest.importorskip('win32security')
    api = pytest.importorskip('win32api')
    import pywintypes
    from pathlib import Path
    token = security.OpenProcessToken(api.GetCurrentProcess(), 8)
    try:
        principal = security.ConvertSidToStringSid(security.GetTokenInformation(token, security.TokenUser)[0])
    finally:
        token.Close()
    spec = definition(principal=principal, executable=str(Path(sys.executable).with_name('pythonw.exe')),
                      working_directory=str(tmp_path), arguments=('-m', 'unused_validation_target'))
    scheduler = win32com.Dispatch('Schedule.Service')
    scheduler.Connect()
    folder = scheduler.GetFolder('\\')
    def absent():
        try:
            folder.GetTask(spec.name)
        except pywintypes.com_error as error:
            codes = {error.hresult, error.excepinfo[5] if error.excepinfo else None}
            if -2147024894 in codes:  # HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)
                return True
            raise
        return False
    assert absent(), 'Validation must not touch any existing task'
    # TASK_VALIDATE_ONLY = 1. Microsoft specifies XML validation without
    # registration; no CREATE/UPDATE flags or start commands are sent.
    folder.RegisterTask(spec.name, windows_logon_task(spec), 1, None, None, 3, None)
    folder.RegisterTask(spec.name, windows_with_enabled(windows_logon_task(spec), False), 1, None, None, 3, None)
    folder.RegisterTask(spec.name, windows_with_execution(windows_logon_task(spec),
        replace(spec, arguments=('-I', '-m', 'unused_upgrade_target', '--token', 'new-token'))), 1, None, None, 3, None)
    assert absent(), 'XML validation unexpectedly registered a task'


def test_enablement_confirmation_preserves_unknown_edits_and_trigger_settings():
    original = windows_logon_task(definition())
    disabled = windows_with_enabled(original, False)
    assert windows_enablement_matches(original, disabled, False)
    assert not windows_enablement_matches(original, disabled, True)
    assert windows_enablement_matches(disabled, windows_with_enabled(disabled, True), True)
    assert not windows_enablement_matches(original, disabled.replace('LeastPrivilege', 'HighestAvailable'), False)
    assert not windows_enablement_matches(original, disabled.replace('IgnoreNew', 'Parallel'), False)
    assert not windows_enablement_matches(original, disabled.replace('</ns0:Settings>', '<ns0:Priority>4</ns0:Priority></ns0:Settings>'), False)
    trigger_edit = disabled.replace('<ns0:Enabled>true</ns0:Enabled>', '<ns0:Enabled>false</ns0:Enabled>')
    assert not windows_enablement_matches(original, trigger_edit, False)


def test_enablement_rejects_ambiguous_input_and_accepts_schema_default():
    original = windows_logon_task(definition())
    no_setting = original.replace('<Enabled>true</Enabled><Hidden>', '<Hidden>')
    assert windows_enablement_matches(original, no_setting, True)
    assert windows_enablement_matches(original, windows_with_enabled(no_setting, False), False)
    with pytest.raises(ValueError):
        windows_with_enabled(original, 'false')
    with pytest.raises(ValueError):
        windows_with_enabled(original.replace('</Settings>', '<Enabled>false</Enabled></Settings>'), False)
    with pytest.raises(ValueError):
        windows_with_enabled('<!DOCTYPE Task []>' + original, False)


def test_execution_update_preserves_native_policy_and_enablement():
    original = windows_with_enabled(windows_logon_task(definition()), False)
    target = definition(executable=r'C:\New environment\pythonw.exe', arguments=('-I', '-m', 'new.entry', 'new-token'))
    changed = windows_with_execution(original, target)
    assert windows_execution_matches(original, changed, target)
    assert 'new-token' in changed and '<ns0:Enabled>false</ns0:Enabled>' in changed
    for old, new in [('LeastPrivilege', 'HighestAvailable'), ('IgnoreNew', 'Parallel'),
                     ('PT0S', 'PT5S'), ('InteractiveToken', 'S4U')]:
        assert not windows_execution_matches(original, changed.replace(old, new), target)
    assert not windows_execution_matches(original, changed.replace('new-token', 'foreign-token'), target)
    assert not windows_execution_matches(original, windows_with_enabled(changed, True), target)


@pytest.mark.parametrize('change', ['duplicate-action', 'duplicate-command', 'entity', 'expansion'])
def test_execution_update_refuses_ambiguous_or_expanding_action(change):
    original = windows_logon_task(definition())
    target = definition()
    if change == 'duplicate-action':
        original = original.replace('</Actions>', '<Exec><Command>x</Command></Exec></Actions>')
    elif change == 'duplicate-command':
        original = original.replace('</Exec>', '<Command>x</Command></Exec>')
    elif change == 'entity':
        original = '<!DOCTYPE Task []>' + original
    else:
        target = definition(executable=r'C:\%OTHER%\pythonw.exe')
    with pytest.raises(ValueError):
        windows_with_execution(original, target)
