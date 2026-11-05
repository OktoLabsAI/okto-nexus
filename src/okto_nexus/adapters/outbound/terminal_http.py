"""Bounded local operator HTTP transport; no provider/agent credentials stored."""
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from ...application.terminal_connection import ConnectionError
from .service_manager.inspection import NoRedirect


class LocalOperatorHTTP:
    def __init__(self, *, host, port, timeout=30):
        if host not in ('127.0.0.1', 'localhost', '0.0.0.0', '::', '::1'):
            raise ConnectionError('LOCAL_CONTROL_UNAVAILABLE', 'The selected service has no loopback operator address.')
        address = '[::1]' if host in ('::', '::1') else '127.0.0.1'
        self.base = f'http://{address}:{port}'
        self.timeout = timeout
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
                'The Server response is unavailable. Resume the saved request; do not create another setup.',
                possible_effect=method != 'GET') from None
        try:
            with response:
                raw = response.read(1048577)
        except (HTTPException, TimeoutError, OSError):
            raise ConnectionError('OUTCOME_UNKNOWN' if method != 'GET' else 'SERVER_UNREACHABLE',
                'The response body was interrupted. Inspect the saved setup before any new submission.',
                possible_effect=method != 'GET') from None
        try:
            if len(raw) > 1048576:
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
