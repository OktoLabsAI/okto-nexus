"""The local owner supplies bounded explicit discovery trust to passive Core."""
import os

import pytest

from okto_nexus.bootstrap.local_discovery import split_discovery_args
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.outbound.execution.core_inventory import discover_local_candidates


def test_passive_path_observation_requires_owner_root_for_trust(tmp_path):
    binary=tmp_path/('codex.exe' if os.name=='nt' else 'codex')
    binary.write_bytes(b'Technical discovery candidate')
    binary.chmod(0o700)
    config,rest=split_discovery_args(['--home','retained','--harness-root='+str(tmp_path),
                                   '--harness-root',str(tmp_path)])
    assert rest==['--home','retained'] and config.trusted_roots==(tmp_path,)
    observed=discover_local_candidates(path_env=str(tmp_path)).candidates
    assert len(observed)==1 and observed[0].trust=='untrusted'
    found=discover_local_candidates(path_env=str(tmp_path),**config.arguments()).candidates
    assert len(found)==1 and found[0].adapter_id=='codex_app_server'
    assert found[0].trust=='selected'
    assert found[0].installation_ref==observed[0].installation_ref


@pytest.mark.parametrize('case',['missing','relative','empty','not_found','file_root','node_directory','unpaired','repeat'])
def test_invalid_discovery_options_fail_before_startup(tmp_path,case):
    node=tmp_path/'node.exe'
    node.write_bytes(b'Technical Node candidate')
    args={
        'missing':['--harness-root'],
        'relative':['--harness-root','.'],
        'empty':['--harness-root='],
        'not_found':['--harness-root',str(tmp_path/'absent')],
        'file_root':['--harness-root',str(node)],
        'node_directory':['--pi-node',str(tmp_path)],
        'unpaired':['--pi-install-root',str(tmp_path)],
        'repeat':['--pi-node',str(node),'--pi-node',str(node)],
    }[case]
    with pytest.raises(OktoNexusError) as refused:
        split_discovery_args(args)
    assert refused.value.code=='CONFIG_ERROR'


def test_pi_pair_is_retained_without_execution(tmp_path):
    node=tmp_path/'node.exe'
    node.write_bytes(b'Technical Node candidate')
    config,rest=split_discovery_args(['--pi-node',str(node),'--pi-install-root',str(tmp_path),
                                    '--harness-root',str(tmp_path)])
    assert config.pi_node==node and config.pi_install_root==tmp_path and not rest
    assert not discover_local_candidates(path_env='',**config.arguments()).candidates
