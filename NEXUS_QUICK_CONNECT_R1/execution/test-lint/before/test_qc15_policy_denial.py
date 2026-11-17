"""B07: existing canonical method denial, reduced authority in an owned DB."""
import hashlib
import json
import os
from pathlib import Path

from test_qc15_cli_choices import cli, terminal, checking, local_setup
from okto_nexus.application.terminal_connection import PREFIX


def all_rows(conn):
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: sorted([tuple(row) for row in conn.execute(
        'SELECT * FROM "' + name.replace('"', '""') + '"')], key=repr) for name in names}


def test_existing_method_denial_is_projected_and_cli_refuses_before_effects(cli, capsys):
    c = cli
    me = c.t.call('GET', PREFIX + '/connections/me')
    subject = me['agent_id']
    executor = c.t.app.state.embedded_inventory_owner.key.executor_id
    route = PREFIX + '/agents/' + subject + '/runtime-options?executor_id=' + executor
    initial = c.t.call('GET', route)
    options = [r for r in initial['options'] if r['adapter_id'] == 'codex_app_server']
    assert initial['adapter_freshness']['codex_app_server'] == 'FRESH'
    assert len(options) == 1 and options[0]['can_configure'] is True
    # This is the existing canonical policy fact used by runtime-options, not
    # an altered response or new access rule. Never increase authority.
    with c.t.deps.connection_factory.unit_of_work() as uow:
        before_seed = all_rows(uow.connection)
        uow.connection.execute(
            'INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES (?,?,0) '
            'ON CONFLICT(agent_id,method) DO UPDATE SET enabled=0',
            (subject, 'codex_app_server'))
        after_seed = all_rows(uow.connection)
    changes = [name for name in before_seed if before_seed[name] != after_seed[name]]
    assert changes == ['agent_connection_methods', 'attention_operation_epochs']
    def own_anchor(row):
        return row[0] == 'authority_agent_connection_methods' and json.loads(row[1]) == [subject, 'codex_app_server']
    anchors_before = before_seed['attention_operation_epochs']
    anchors_after = after_seed['attention_operation_epochs']
    assert [row for row in anchors_before if not own_anchor(row)] == [row for row in anchors_after if not own_anchor(row)]
    assert not [row for row in anchors_before if own_anchor(row)]
    anchor, = [row for row in anchors_after if own_anchor(row)]
    assert anchor[2] == 'present' and anchor[3] == 1
    assert anchor[4] == anchor[5] and anchor[4]
    original_other = [row for row in before_seed['agent_connection_methods']
                      if row[:2] != (subject, 'codex_app_server')]
    actual_other = [row for row in after_seed['agent_connection_methods']
                    if row[:2] != (subject, 'codex_app_server')]
    assert original_other == actual_other
    assert (subject, 'codex_app_server', 0) in after_seed['agent_connection_methods']
    denied = c.t.call('GET', route)
    selected, = [r for r in denied['options'] if r['adapter_id'] == 'codex_app_server']
    assert denied['adapter_freshness']['codex_app_server'] == 'FRESH'
    assert selected['candidate_ref'] == options[0]['candidate_ref']
    assert selected['can_configure'] is False and 'METHOD_DISABLED' in selected['policy_reasons']
    # Canonical identity reads materialize the policy's new authorization
    # revision. Establish the already-denied baseline after that real read;
    # never patch a revision counter or ignore its authority anchor.
    assert c.t.call('GET', PREFIX + '/connections/me')['agent_id'] == subject
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        before_cli = all_rows(uow.connection)
    capsys.readouterr()
    code = c.run(['connect','codex','App','--profile','denied','--plan','--json'])
    value = json.loads(capsys.readouterr().out)
    assert code == 3 and value['code'] == 'CONFIGURATION_NOT_AUTHORIZED'
    assert c.t.probes == c.t.turns == []
    assert not list(c.home.glob('terminal/profiles/*.json'))
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        after_cli = all_rows(uow.connection)
    changed = [name for name in before_cli if before_cli[name] != after_cli[name]]
    assert changed == [], changed
    # Public hashes/counts only; no rows, credentials, or private metadata.
    proof = dict(subject=subject, table_count=len(before_cli),
        seeded_tables=changes, cli_changed_tables=changed,
        policy_reason='METHOD_DISABLED', freshness='FRESH', can_configure=False,
        refusal=value['code'], tests=0, probes=0,
        table_hashes={name:hashlib.sha256(repr(rows).encode()).hexdigest()
                      for name,rows in before_cli.items()})
    if os.environ.get('QC_DERIVATIVE_OUTPUT'):
        (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'policy-proof.json').write_text(
            json.dumps(proof,indent=2)+'\n',encoding='utf-8')
