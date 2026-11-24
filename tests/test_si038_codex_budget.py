import json

import pytest

from tools.si038_codex_budget import BudgetStop, CampaignBudget


def records(budget):
    return [json.loads(line) for line in budget.path.read_text(encoding='utf-8').splitlines()]


def begin_interactive(budget):
    budget.reserve('setup', 'setup-intent')
    budget.observe('setup', 105, terminal=True)
    budget.reserve('home', 'home-intent')
    budget.observe('home', 210, terminal=True)
    budget.reserve('interactive', 'interactive-intent')


def test_reserve_queue_and_steer_during_one_active_turn(tmp_path):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.observe('interactive', 120_000)
    budget.reserve('queued', 'queued-intent')
    budget.reserve('steer', 'steer-intent')
    budget.observe('interactive', 165_000, terminal=True)
    budget.observe('queued', 2_000, terminal=True)
    reserved = [event for event in records(budget) if event['event'] == 'reserved']
    assert [event['step'] for event in reserved] == ['setup', 'home', 'interactive', 'queued', 'steer']
    assert reserved[-2]['charged'] == 345_000
    assert reserved[-1]['charged'] == 375_000
    last = records(budget)[-1]
    assert last['observed'] == 167_315
    assert last['charged'] == 390_000
    assert last['final_billing'] is False


def test_queue_provision_survives_lost_admission_response(tmp_path):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.reserve('queued', 'queued-intent')
    with pytest.raises(BudgetStop, match='EFFECT_OR_USAGE_UNCERTAIN'):
        budget.stop_uncertain()
    with pytest.raises(BudgetStop, match='CAMPAIGN_STOPPED'):
        budget.reserve('steer', 'steer-intent')
    with pytest.raises(BudgetStop, match='CAMPAIGN_ALREADY_STARTED'):
        CampaignBudget(tmp_path)
    assert records(budget)[-2]['charged'] == 300_000
    assert records(budget)[-2]['intent_id'] == 'queued-intent'


def test_accounting_cannot_be_assumed_from_reservation(tmp_path):
    budget = CampaignBudget(tmp_path)
    budget.reserve('setup', 'setup-intent')
    with pytest.raises(BudgetStop, match='PREVIOUS_ACCOUNTING_UNCONFIRMED'):
        budget.reserve('home', 'home-intent')
    assert [event['event'] for event in records(budget)] == ['opened', 'reserved', 'stopped']


def test_reserve_is_refused_before_preventive_budget_would_be_crossed(tmp_path):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.observe('interactive', 240_000)
    with pytest.raises(BudgetStop, match='PREVENTIVE_BUDGET_REACHED'):
        budget.reserve('queued', 'queued-intent')
    assert not any(event.get('step') == 'queued' for event in records(budget))


@pytest.mark.parametrize(('tokens', 'reason'), [(450_000, 'PREVENTIVE_BUDGET_REACHED'), (500_000, 'OBSERVED_BUDGET_STOP')])
def test_late_token_report_is_preserved_when_it_crosses_budget(tmp_path, tokens, reason):
    budget = CampaignBudget(tmp_path)
    budget.reserve('setup', 'setup-intent')
    budget.observe('setup', 105, terminal=True)
    with pytest.raises(BudgetStop, match=reason):
        budget.observe('setup', tokens)
    observed, stopped = records(budget)[-2:]
    assert observed['observed'] == tokens and observed['terminal'] is True
    assert stopped == {'event': 'stopped', 'reason': reason}
    with pytest.raises(BudgetStop, match='CAMPAIGN_STOPPED'):
        budget.reserve('home', 'home-intent')


@pytest.mark.parametrize(('fall', 'reason'), [('counter', 'USAGE_COUNTER_UNKNOWN_OR_REGRESSED'),
                                             ('finished', 'INTERACTIVE_TURN_ALREADY_FINISHED'),
                                             ('queued', 'QUEUED_TURN_ALREADY_STARTED')])
def test_uncertain_or_out_of_order_control_blocks_new_admission(tmp_path, fall, reason):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.observe('interactive', 300)
    budget.reserve('queued', 'queued-intent')
    with pytest.raises(BudgetStop, match=reason):
        if fall == 'counter':
            budget.observe('interactive', 299)
        else:
            if fall == 'queued':
                budget.observe('queued', 1)
            else:
                budget.observe('interactive', 300, terminal=True)
            budget.reserve('steer', 'steer-intent')
    assert not any(event.get('step') == 'steer' for event in records(budget))


def test_budget_has_only_one_writer_and_retains_partial_file(tmp_path):
    partial = tmp_path / 'si038-budget.jsonl'
    partial.write_bytes(b'{"event":"reserved')
    with pytest.raises(BudgetStop, match='CAMPAIGN_ALREADY_STARTED'):
        CampaignBudget(tmp_path)
    assert partial.read_bytes() == b'{"event":"reserved'


def test_duplicate_intent_cannot_reserve_a_different_step(tmp_path):
    budget = CampaignBudget(tmp_path)
    budget.reserve('setup', 'same-intent')
    budget.observe('setup', 100, terminal=True)
    with pytest.raises(BudgetStop, match='INTENT_INVALID_OR_ALREADY_RESERVED'):
        budget.reserve('home', 'same-intent')
    assert [event['step'] for event in records(budget) if event['event'] == 'reserved'] == ['setup']


def test_failed_durable_write_stops_admission(tmp_path, monkeypatch):
    budget = CampaignBudget(tmp_path)

    def fail(_):
        raise OSError('fixture fsync failure')

    monkeypatch.setattr('tools.si038_codex_budget.os.fsync', fail)
    with pytest.raises(BudgetStop, match='BUDGET_RECORD_NOT_DURABLE'):
        budget.reserve('setup', 'setup-intent')
    with pytest.raises(BudgetStop, match='CAMPAIGN_STOPPED'):
        budget.reserve('setup', 'setup-intent')
    with pytest.raises(BudgetStop, match='CAMPAIGN_ALREADY_STARTED'):
        CampaignBudget(tmp_path)
