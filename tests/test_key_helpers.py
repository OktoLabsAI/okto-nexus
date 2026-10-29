"""Focused edge-case tests for API key helper boundaries.

The broader API-key flow and common malformed-string cases live in
`test_agent_keys.py`; this module covers cases not exercised there.
"""

import pytest

from okto_nexus.domain.keys import (
    generate_api_key,
    hash_api_key,
    is_well_formed_api_key,
)


def test_is_well_formed_api_key_rejects_uppercase_hex():
    assert not is_well_formed_api_key("nxs_" + "A" * 48)


@pytest.mark.parametrize("value", [None, 123])
def test_is_well_formed_api_key_rejects_non_string_values(value):
    assert not is_well_formed_api_key(value)


def test_hash_api_key_is_stable_for_the_same_key():
    key = "nxs_" + "0" * 48

    assert hash_api_key(key) == hash_api_key(key)


def test_plaintext_api_key_is_not_equal_to_its_hash():
    key = generate_api_key()

    assert key != hash_api_key(key)


def test_hash_is_not_a_well_formed_api_key():
    key_hash = hash_api_key(generate_api_key())

    assert not is_well_formed_api_key(key_hash)
