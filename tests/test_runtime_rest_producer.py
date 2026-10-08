"""REST steering uses canonical transactional inbox/outbox admission."""
import pytest

from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.errors import ErrorCode, OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, open_rest, wait_sent
from test_runtime_delivery_acceptance import counts

runtime = runtime_fixture
