import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.application.terminal_connection import ConnectionError


@pytest.mark.parametrize('fault', ['invalid_json', 'oversized', 'lost_body', 'malformed_error'])
def test_mutating_response_failure_remains_uncertain(fault):
    http = LocalOperatorHTTP(host='127.0.0.1', port=8202)
    if fault == 'invalid_json':
        response = io.BytesIO(b'not json')
    elif fault == 'oversized':
        response = io.BytesIO(b' ' * 1048577)
    elif fault == 'lost_body':
        class Lost(io.BytesIO):
            def read(self, count):
                raise OSError('interrupted')
        response = Lost()
    else:
        response = HTTPError(http.base, 409, 'malformed', {}, io.BytesIO(b'{"error":[]}'))
    def open_response(*args, **kwargs):
        if isinstance(response, HTTPError):
            raise response
        return response
    http.opener = SimpleNamespace(open=open_response)
    with pytest.raises(ConnectionError) as failure:
        http('POST', '/api/v1/runtime-management/connections/setup:finish', {})
    assert failure.value.possible_effect


def test_canonical_missing_receipt_preserves_stage_without_replay():
    http = LocalOperatorHTTP(host='::1', port=8202)
    calls = []
    def failed(request, **kwargs):
        calls.append(request)
        value = {'error': {'code': 'NOT_FOUND', 'message': 'No commit', 'stage': 'connection.setup_commit'}}
        raise HTTPError(http.base, 404, 'not found', {}, io.BytesIO(json.dumps(value).encode()))
    http.opener = SimpleNamespace(open=failed)
    with pytest.raises(ConnectionError) as failure:
        http('POST', '/api/v1/runtime-management/connections/setup:recover', {})
    assert (failure.value.code, failure.value.stage) == ('NOT_FOUND', 'connection.setup_commit')
    assert len(calls) == 1 and calls[0].full_url.startswith('http://[::1]:8202/')
    assert calls[0].get_header('X-nexus-ui') == '1'
    assert calls[0].get_header('Authorization') is None


def test_remote_address_is_not_treated_as_a_local_operator():
    with pytest.raises(ConnectionError, match='loopback'):
        LocalOperatorHTTP(host='example.test', port=8202)


def test_work_transport_fits_the_servers_bounded_output_after_json_escaping():
    value = {'result': {'output_text': '\x00' * 1048576}}
    raw = json.dumps(value).encode('utf-8')
    assert len(raw) > 6 * 1048576
    http = LocalOperatorHTTP(host='127.0.0.1', port=8202, max_response_bytes=8 * 1048576)
    http.opener = SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(raw))
    assert http('GET', '/api/v1/runtime-management/runtime/operations/operation') == value
