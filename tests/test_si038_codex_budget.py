import json

import pytest

from tools.si038_codex_budget import BudgetStop, CampaignBudget
from tools.si038_codex_usage import TurnUsage, UnconfirmedUsage


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


@pytest.mark.parametrize('late_total', [374_999, 375_000])
def test_completed_turn_is_read_again_before_admitting_first_work(tmp_path, late_total):
    budget = CampaignBudget(tmp_path)
    budget.reserve('setup', 'setup-intent')
    reports = iter([TurnUsage('setup-turn', 105, 'success'), TurnUsage('setup-turn', late_total, 'success')])
    budget.bind_completed_usage('setup', lambda: next(reports))
    if late_total == 375_000:
        with pytest.raises(BudgetStop, match='PREVENTIVE_BUDGET_REACHED'):
            budget.reserve('home', 'home-intent')
        assert records(budget)[-1]['event'] == 'stopped'
        assert not any(item.get('step') == 'home' for item in records(budget))
    else:
        budget.reserve('home', 'home-intent')
        assert records(budget)[-1]['charged'] == 449_999
    late = records(budget)[-2]
    assert late['event'] == 'observed' and late['group_tokens'] == late_total
    assert late['turn_id'] == 'setup-turn'


@pytest.mark.parametrize('new_report', [
    None,
    TurnUsage('different-turn', 105, 'success'),
    TurnUsage('setup-turn', 105, None),
    UnconfirmedUsage('JOURNAL_COVERAGE_GAP'),
], ids=['missing', 'different-turn', 'terminal-unconfirmed', 'journal-unreadable'])
def test_uncertain_refresh_stops_reservation_without_replacing_observation(tmp_path, new_report):
    budget = CampaignBudget(tmp_path)
    budget.reserve('setup', 'setup-intent')
    reports = iter([TurnUsage('setup-turn', 105, 'success'), new_report])

    def read():
        report = next(reports)
        if isinstance(report, Exception):
            raise report
        return report

    budget.bind_completed_usage('setup', read)
    with pytest.raises(BudgetStop, match='EFFECT_OR_USAGE_UNCERTAIN'):
        budget.reserve('home', 'home-intent')
    assert [item['event'] for item in records(budget)] == ['opened', 'reserved', 'observed', 'stopped']
    assert records(budget)[-2]['group_tokens'] == 105


def test_late_home_usage_blocks_steer_and_retains_the_queue_reservation(tmp_path):
    budget = CampaignBudget(tmp_path)
    budget.reserve('setup', 'setup-intent')
    budget.bind_completed_usage('setup', lambda: TurnUsage('setup-turn', 105, 'success'))
    budget.reserve('home', 'home-intent')
    home_total = 210
    budget.bind_completed_usage('home', lambda: TurnUsage('home-turn', home_total, 'success'))
    budget.reserve('interactive', 'interactive-intent')
    budget.reserve('queued', 'queued-intent')
    home_total = 150_000

    with pytest.raises(BudgetStop, match='PREVENTIVE_BUDGET_REACHED'):
        budget.reserve('steer', 'steer-intent')

    entries = records(budget)
    assert entries[-2]['group'] == 'home' and entries[-2]['group_tokens'] == 150_000
    assert entries[-2]['charged'] == 375_000
    assert [entry['step'] for entry in entries if entry['event'] == 'reserved'] == [
        'setup', 'home', 'interactive', 'queued']


@pytest.mark.parametrize('tokens', [225_000, 240_000])
def test_reserve_is_refused_when_it_would_reach_the_preventive_budget(tmp_path, tokens):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.observe('interactive', tokens)
    with pytest.raises(BudgetStop, match='PREVENTIVE_BUDGET_REACHED'):
        budget.reserve('queued', 'queued-intent')
    assert not any(event.get('step') == 'queued' for event in records(budget))


def test_reservation_below_the_preventive_budget_is_recorded(tmp_path):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.observe('interactive', 224_999)
    budget.reserve('queued', 'queued-intent')
    assert records(budget)[-1]['charged'] == 449_999


def test_usage_plus_existing_provisions_stops_at_the_preventive_budget(tmp_path):
    budget = CampaignBudget(tmp_path)
    begin_interactive(budget)
    budget.observe('interactive', 200_000)
    budget.reserve('queued', 'queued-intent')
    with pytest.raises(BudgetStop, match='PREVENTIVE_BUDGET_REACHED'):
        budget.observe('interactive', 225_000)
    observed, stopped = records(budget)[-2:]
    assert observed['observed'] == 225_315 and observed['charged'] == 450_000
    assert stopped == {'event': 'stopped', 'reason': 'PREVENTIVE_BUDGET_REACHED'}
    with pytest.raises(BudgetStop, match='CAMPAIGN_STOPPED'):
        budget.reserve('steer', 'steer-intent')


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
