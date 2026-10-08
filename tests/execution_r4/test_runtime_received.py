"""Only native acceptance records receipt, without consuming MCP deliveries."""
import sqlite3
import pytest
from okto_nexus.application.execution_domain_delivery import project_delivery_receipt


@pytest.fixture
def deliveries():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE execution_delivery_releases(domain_operation_id);
        CREATE TABLE execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id);
        CREATE TABLE delivery_outbox(operation_id,delivery_id,message_id,recipient_agent_id,
            reconciliation_id,status,ack_level,canonical_terminal_operation_id,updated_at);
        CREATE TABLE message_deliveries(delivery_id,message_id,recipient_agent_id,
            consumer_kind,consumer_operation_id,status,delivered_at,read_at);
        INSERT INTO execution_domain_deliveries VALUES ('server','executor','turn','domain');
        INSERT INTO delivery_outbox VALUES ('domain','delivery','message','agent',NULL,'PENDING',NULL,NULL,NULL);
        INSERT INTO message_deliveries VALUES ('delivery','message','agent','push','domain','unread',NULL,NULL);
    ''')
    yield conn
    conn.close()


def project(conn, stage, action='turn.submit'):
    project_delivery_receipt(conn, server_id='server', executor_id='executor',
                             operation_id='turn', action=action, stage=stage)


@pytest.mark.parametrize('stage', ['SUBMITTED','RUNNING','SUCCEEDED'])
def test_receipt_records_first_native_acceptance_without_ack(deliveries, stage):
    project(deliveries, stage)
    status, received, read = deliveries.execute('SELECT status,delivered_at,read_at FROM message_deliveries').fetchone()
    assert status == 'delivered' and received and read is None
    deliveries.execute("UPDATE message_deliveries SET status='read',read_at='later'")
    project(deliveries, 'SUCCEEDED')
    assert tuple(deliveries.execute('SELECT status,delivered_at,read_at FROM message_deliveries').fetchone()) == ('read',received,'later')


@pytest.mark.parametrize('stage', ['ACCEPTED','FAILED','CANCELLED','OUTCOME_UNKNOWN'])
def test_non_acceptance_does_not_claim_receipt(deliveries, stage):
    project(deliveries, stage)
    assert tuple(deliveries.execute('SELECT status,delivered_at,read_at FROM message_deliveries').fetchone()) == ('unread',None,None)


@pytest.mark.parametrize('change', [
    "UPDATE message_deliveries SET consumer_kind='pull'",
    "UPDATE message_deliveries SET consumer_operation_id='another'",
    "UPDATE delivery_outbox SET reconciliation_id='reconciled'",
    "UPDATE delivery_outbox SET recipient_agent_id='another'",
])
def test_native_receipt_cannot_take_over_other_consumers(deliveries, change):
    deliveries.execute(change)
    project(deliveries, 'SUBMITTED')
    assert tuple(deliveries.execute('SELECT status,delivered_at,read_at FROM message_deliveries').fetchone()) == ('unread',None,None)


def test_opening_a_session_does_not_mean_message_received(deliveries):
    project(deliveries, 'SUBMITTED', action='runtime.open')
    assert tuple(deliveries.execute('SELECT delivered_at FROM message_deliveries').fetchone()) == (None,)
