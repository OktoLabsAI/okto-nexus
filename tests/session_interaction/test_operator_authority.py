"""Operator references are private, persistent links to individual sessions."""

import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.http import operator_auth


def test_authority_references_survive_restart_and_logout_only_the_exact_session(tmp_path):
    auth = operator_auth.OperatorAuth(tmp_path)
    assert auth.configure("fixture-operator", "fixture-password", local=True)
    first = auth.login("fixture-operator", "fixture-password")
    second = auth.login("fixture-operator", "fixture-password")
    assert first and second and first != second
    first_ref = auth.authority_reference(first)
    second_ref = auth.authority_reference(second)
    assert first_ref and second_ref and first_ref != second_ref

    first_digest = hashlib.sha256(first.encode()).hexdigest()
    assert first_ref not in {first, first_digest}
    assert auth.resolve(first_ref) is None
    assert auth.resolve_authority(first) is None
    assert auth.resolve_authority(first_digest) is None
    assert auth.authority_reference("invalid-cookie") is None

    reopened = operator_auth.OperatorAuth(tmp_path)
    assert reopened.authority_reference(first) == first_ref
    assert reopened.resolve_authority(first_ref) == "fixture-operator"
    assert reopened.resolve_authority(second_ref) == "fixture-operator"

    reopened.logout(first)
    assert auth.resolve(first) is None
    assert auth.authority_reference(first) is None
    assert auth.resolve_authority(first_ref) is None
    assert auth.resolve(second) == "fixture-operator"
    assert auth.resolve_authority(second_ref) == "fixture-operator"


def test_authority_references_expire_and_credential_rotation_clears_remaining_sessions(tmp_path, monkeypatch):
    now = 1000
    monkeypatch.setattr(operator_auth, "time", SimpleNamespace(time=lambda: now))
    auth = operator_auth.OperatorAuth(tmp_path)
    assert auth.configure("fixture-operator", "fixture-password", local=True)
    first = auth.login("fixture-operator", "fixture-password")
    first_ref = auth.authority_reference(first)
    assert first_ref and auth.resolve_authority(first_ref)

    now += operator_auth.SESSION_SECONDS - 1
    current = auth.login("fixture-operator", "fixture-password")
    current_ref = auth.authority_reference(current)
    assert current_ref and auth.resolve_authority(current_ref)
    now += 1
    assert auth.resolve_authority(first_ref) is None
    assert auth.authority_reference(first) is None
    assert auth.resolve_authority(current_ref) == "fixture-operator"

    assert auth.configure("fixture-operator", "updated-fixture-password", current_password="fixture-password")
    assert auth.resolve_authority(current_ref) is None
    renewed = auth.login("fixture-operator", "updated-fixture-password")
    renewed_ref = auth.authority_reference(renewed)
    assert renewed_ref and renewed_ref not in {first_ref, current_ref}
    assert auth.resolve_authority(renewed_ref) == "fixture-operator"


def test_claim_fence_excludes_revocation_and_checks_current_expiry(tmp_path, monkeypatch):
    now = 1000
    monkeypatch.setattr(operator_auth, "time", SimpleNamespace(time=lambda: now))
    auth = operator_auth.OperatorAuth(tmp_path)
    assert auth.configure("fixture-operator", "fixture-password", local=True)
    token = auth.login("fixture-operator", "fixture-password")
    reference = auth.authority_reference(token)
    contender = sqlite3.connect(auth.path, timeout=0)
    try:
        with auth.authority_fence() as resolve:
            assert resolve(reference) == "fixture-operator"
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                contender.execute("DELETE FROM sessions")
            now += operator_auth.SESSION_SECONDS
            assert resolve(reference) is None
        contender.execute("DELETE FROM sessions")
        contender.commit()
    finally:
        contender.close()
    now = 1000
    assert auth.resolve_authority(reference) is None
