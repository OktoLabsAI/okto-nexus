import pytest
from nexus_connector_core import CoreError
from okto_nexus.application.connection_authorization import normalize_authorization


@pytest.mark.parametrize('limits,expected', [
    ({'minutes': 0, 'actions': 0, 'no_expiry': True, 'unlimited_actions': True}, {'minutes': None, 'actions': None}),
    ({'minutes': 0, 'actions': 20}, {'minutes': None, 'actions': 20}),
    ({'minutes': 60, 'actions': 0}, {'minutes': 60, 'actions': None}),
    ({'minutes': 60, 'actions': 20}, {'minutes': 60, 'actions': 20}),
])
def test_limits(limits, expected):
    assert normalize_authorization({'authorization': limits})['authorization'] == expected


@pytest.mark.parametrize('limits', [
    {'minutes': 60, 'actions': 20, 'no_expiry': True},
    {'minutes': 0, 'actions': 20, 'no_expiry': False},
    {'minutes': False, 'actions': 20},
    {'minutes': 0, 'actions': 0, 'unlimited_actions': 1},
])
def test_reject_contradictions(limits):
    with pytest.raises(CoreError):
        normalize_authorization({'authorization': limits})
