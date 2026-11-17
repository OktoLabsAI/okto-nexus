import json
from types import SimpleNamespace
import pytest
from okto_nexus.adapters.inbound.cli.connect_arguments import parse_connect_args
from okto_nexus.adapters.inbound.cli import connect, quick_connect_selection
from okto_nexus.application.terminal_connection import ConnectionError

@pytest.mark.parametrize('flags', [[], ['--plan'], ['--json'], ['--no-chat'],
    ['--timeout','12'], ['--start-at-login'], ['codex'], ['codex','Project'],
    ['--id','reviewer'], ['codex','--project','C:/owned'], ['codex','--client','codex'],
    ['--id','reviewer','--profile','existing']])
def test_public_entry(flags):
    args, _ = parse_connect_args(flags)
    assert connect._quick_entry_requested(args) is True

@pytest.mark.parametrize('flags', [['--profile','existing'], ['--project','C:/owned'],
    ['--client','codex'], ['--agent','a'], ['--new-agent','b'], ['--name','Named'],
    ['--workspace-id','w'], ['--binding-id','b'], ['--candidate-ref','c'],
    ['--provider-home','C:/owned'], ['--operator-profile','remote'],
    ['--remote-draft','C:/owned'], ['--setup-receipt-output','C:/owned'],
    ['--approve','revision'], ['--new-connection'], ['--review-current']])
def test_legacy_selectors(flags):
    args, _ = parse_connect_args(flags)
    assert connect._quick_entry_requested(args) is False

@pytest.mark.parametrize('flags,checkpoint', [([],False),(['codex'],False),
    (['--id','reviewer'],False),(['--profile','retained'],True)])
def test_quick_route_and_saved_checkpoint_reach_prepare(tmp_path, monkeypatch, capsys, flags, checkpoint):
    home = tmp_path/'home'
    if checkpoint:
        target=home/'terminal/profiles/retained.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'selection':{'quick_connect':{'version':1}}}))
    service=SimpleNamespace(adapter=SimpleNamespace(home=home,host='127.0.0.1',port=1),
        ensure_running=lambda **kwargs: {'state':'ready'}, inspect=lambda: {'state':'ready'})
    monkeypatch.setattr(connect,'resolve_local_service',lambda args:service)
    monkeypatch.setattr(connect.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    calls=[]
    def prepare(*args,**kwargs):
        calls.append(kwargs.get('saved'))
        raise ConnectionError('QUICK_ROUTE_SENTINEL','No HTTP, provider or setup effects')
    monkeypatch.setattr(quick_connect_selection,'prepare',prepare)
    assert connect.run_connect([*flags,'--home',str(home),'--json','--plan'])==3
    assert len(calls)==1
    assert 'QUICK_ROUTE_SENTINEL' in capsys.readouterr().out
    assert bool(calls[0]) is checkpoint
