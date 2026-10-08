"""An already-open writer-v1 cannot bypass external work proof after upgrade."""
import sqlite3

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_attach_work_channel import admitted, complete_fixture_work

runtime = runtime_fixture
