from copy import deepcopy

from okto_nexus.application.project_preset_update import merge_defaults


def test_versioned_defaults_preserve_custom_values_and_remove_only_unchanged_owned_fields():
    old = dict(harness_settings=dict(model='old', effort='medium'), session_policy='per_sender')
    current = dict(harness_settings=dict(model='custom', effort='medium', extra='kept'), session_policy='per_sender')
    recommended = dict(harness_settings=dict(model='new', verbosity='low'), session_policy='per_sender_session')
    before = deepcopy((current, old, recommended))
    proposed, changes, preserved = merge_defaults(current, old, recommended)
    assert proposed == dict(harness_settings=dict(model='custom', verbosity='low', extra='kept'), session_policy='per_sender_session')
    assert {row['field'] for row in changes} == {'harness_settings.effort', 'harness_settings.verbosity', 'session_policy'}
    assert preserved == [dict(field='harness_settings.model', current='custom', recommendation='new')]
    assert (current, old, recommended) == before


def test_adopting_a_preset_without_a_known_base_preserves_existing_choices():
    current = dict(runtime_enabled=False, harness_settings={'model': 'chosen'})
    proposed, changes, preserved = merge_defaults(current, None,
        dict(runtime_enabled=True, harness_settings={'model': 'new', 'effort': 'high'}))
    assert proposed == current and changes == []
    assert {row['field'] for row in preserved} == {'runtime_enabled', 'harness_settings.model', 'harness_settings.effort'}
