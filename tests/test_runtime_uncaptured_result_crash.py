"""No invented completion/replay when native output never reached the journal."""
import json
import time

import httpx
import pytest

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, PeerWitness, native_records
