"""Synthetic terminal SQL facts reuse the existing Home fixture, not a harness."""
from home_evolution.fixtures import OPERATOR, WORKSPACES, home_scenario
from home_evolution.test_home_queries import service


def test_standalone_sql_null_comparison_never_implies_historical_task(service, home_scenario):
    before = home_scenario.counts()
    values = service.read(context=OPERATOR, section='results', filters={'workspace_id': WORKSPACES[0]})['items']
    assert len(values) == 1
    result = values[0]
    assert result['outcome'] == 'SUCCEEDED'
    assert result['verification_state'] == 'historical_claim'  # Legacy meaning is retained.
    semantics = result['delivery_semantics']
    assert semantics['scope'] == 'turn' and semantics['execution_outcome'] == 'succeeded'
    assert semantics['task_state'] == semantics['verification'] == 'not_applicable'
    assert not semantics['historical'] and semantics['cleanup'] == 'pending'
    assert home_scenario.counts() == before


__all__ = ['home_scenario', 'service']
