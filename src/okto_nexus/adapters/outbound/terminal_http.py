"""Bounded local operator HTTP transport; no provider/agent credentials stored."""
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from ...application.terminal_connection import ConnectionError
from .service_manager.inspection import NoRedirect


class LocalOperatorHTTP:
    def __init__(self, *, host, port, timeout=30, max_response_bytes=1048576):
        if host not in ('127.0.0.1', 'localhost', '0.0.0.0', '::', '::1'):
            raise ConnectionError('LOCAL_CONTROL_UNAVAILABLE', 'The selected service has no loopback operator address.')
        address = '[::1]' if host in ('::', '::1') else '127.0.0.1'
        self.base = f'http://{address}:{port}'
        self.timeout = timeout
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 8 * 1048576:
            raise ConnectionError('RESPONSE_LIMIT_INVALID', 'The operator response bound is invalid.')
        self.max_response_bytes = max_response_bytes
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def __call__(self, method, path, body=None):
        if not path.startswith('/api/v1/') or '?' in path.split('/api/v1/', 1)[0]:
            raise ConnectionError('INVALID_ROUTE', 'A canonical operator API route is required.')
        request = Request(self.base + path, method=method,
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers={'Content-Type': 'application/json', 'X-Nexus-UI': '1'})
        failed = False
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except HTTPError as error:
            response, failed = error, True
        except (URLError, TimeoutError, OSError):
            raise ConnectionError('OUTCOME_UNKNOWN' if method != 'GET' else 'SERVER_UNREACHABLE',
                'The Server response is unavailable. Inspect or resume the same saved request.',
                possible_effect=method != 'GET') from None
        try:
            with response:
                raw = response.read(self.max_response_bytes + 1)
        except (HTTPException, TimeoutError, OSError):
            raise ConnectionError('OUTCOME_UNKNOWN' if method != 'GET' else 'SERVER_UNREACHABLE',
                'The response body was interrupted. Inspect the saved request before any new submission.',
                possible_effect=method != 'GET') from None
        try:
            if len(raw) > self.max_response_bytes:
                raise ValueError()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise ConnectionError('RESPONSE_UNCONFIRMED', 'The Server returned an invalid or oversized response.',
                                  possible_effect=method != 'GET') from None
        if failed:
            error = value.get('error', {})
            if not isinstance(error, dict):
                raise ConnectionError('RESPONSE_UNCONFIRMED', 'The Server error response is malformed.', possible_effect=method != 'GET')
            raise ConnectionError(error.get('code', 'REQUEST_REFUSED'), error.get('message', 'The Server refused this request.'),
                stage=error.get('stage', 'http'), possible_effect=error.get('possible_effect', False))
        return value
