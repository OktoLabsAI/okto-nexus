"""Real owner death after atomic projection/checkpoint commit, before publication."""
from contextlib import closing
import json
import sqlite3
import time

import httpx
import pytest

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, PeerWitness, native_records
