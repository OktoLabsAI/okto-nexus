"""A subdirectory cannot make its repository's own executable trusted."""
import os

from okto_nexus.adapters.outbound.git_project_hint import _origin_name, _trusted_git
from okto_nexus.domain.quick_connect import NameDiscovery


def test_absolute_path_executable_inside_parent_repository_is_not_trusted(tmp_path, monkeypatch):
    repo = tmp_path / 'repository'
    (repo / '.git').mkdir(parents=True)
    root = repo / 'apps' / 'api'
    root.mkdir(parents=True)
    binaries = repo / 'tools'
    binaries.mkdir()
    fake = binaries / ('git.exe' if os.name == 'nt' else 'git')
    fake.write_bytes(b'Untrusted test fixture, never executed')
    fake.chmod(0o755)
    monkeypatch.chdir(root)
    monkeypatch.setenv('PATH', str(binaries))
    assert _trusted_git(root) is None


def test_encoded_separator_in_parent_origin_component_is_ambiguous():
    assert _origin_name('https://example.invalid/org%2Frepo/project.git') is None
    assert _origin_name('ssh://example.invalid/org%5Cname/project.git') is None


def test_cleanup_uncertainty_has_a_fixed_safe_public_reason():
    assert NameDiscovery(status='unconfirmed', reason='git_cleanup_unconfirmed').reason == 'git_cleanup_unconfirmed'
