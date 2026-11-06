"""Origin-bound human operator sessions, held only in the protected OS vault."""
import hashlib
from http.cookies import SimpleCookie
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler

from ...application.terminal_connection import ConnectionError, PREFIX
from .provider_vault import open_backend
from .service_manager.context import read_json, atomic_json
from .service_manager.inspection import NoRedirect
from .terminal_http import LocalOperatorHTTP

COOKIE = 'nexus_operator_session'


def server_origin(value):
    try:
        parsed = urlsplit(value)
        if (not isinstance(value, str) or any(ord(c) < 33 or ord(c) == 127 for c in value) or
                parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or
                parsed.password is not None or parsed.path not in ('', '/') or parsed.query or parsed.fragment or
                '\\' in value or parsed.port == 0):
            raise ValueError()
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        if parsed.scheme == 'http' and host not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError()
        port = parsed.port
        authority = '[' + host + ']' if ':' in host else host
        if port and port != (443 if parsed.scheme == 'https' else 80):
            authority += ':' + str(port)
        return parsed.scheme + '://' + authority
    except (ValueError, TypeError, UnicodeError, AttributeError):
        raise ConnectionError('SERVER_ORIGIN_INVALID', 'Use an HTTPS Server origin without credentials, path, query or fragment; HTTP is limited to loopback.') from None


def session_token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', value):
        raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'The operator session is unavailable. Sign in again.')
    return value


class OperatorProfile:
    def __init__(self, home, name, *, backend=None):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
            raise ConnectionError('PROFILE_INVALID', 'Use 1..80 letters, digits, hyphens or underscores for the operator profile.')
        self.home, self.name, self.backend = Path(home).expanduser().resolve(), name, backend
        self.path = self.home / 'terminal/operators' / (name + '.json')

    def read(self):
        value = read_json(self.path)
        if (value.get('format') != 1 or value.get('origin') != server_origin(value.get('origin')) or
                not isinstance(value.get('server_id'), str) or not value['server_id'] or
                not isinstance(value.get('username'), str) or not value['username']):
            raise ConnectionError('PROFILE_INVALID', 'The operator profile is invalid; inspect its origin and Server identity.')
        return value

    def secret(self, operation, origin, value=None):
        root = os.path.normcase(str(self.home))
        service = 'okto-nexus/operator/' + hashlib.sha256((root + '\0' + self.name + '\0' + server_origin(origin)).encode()).hexdigest()
        try:
            backend = self.backend or open_backend()
            if operation == 'set':
                backend.set(service, 'session', session_token(value))
            elif operation == 'remove':
                backend.remove(service, 'session')
            else:
                return session_token(backend.get(service, 'session'))
        except Exception:
            raise ConnectionError('OPERATOR_VAULT_UNAVAILABLE', 'The protected operator session is unavailable. Unlock the OS vault or sign in again; no file fallback was used.') from None

    def client(self):
        value = self.read()
        return RemoteOperatorHTTP(value['origin'], token=self.secret('get', value['origin']),
                                  server_id=value['server_id'], username=value['username'])

    def login(self, origin, username, password):
        origin = server_origin(origin)
        previous = self.read() if self.path.exists() else None
        if previous and previous['origin'] != origin:
            raise ConnectionError('PROFILE_CONFLICT', 'This operator profile names another Server origin. Choose a new profile.')
        # Fail before authentication if the protected store cannot be opened.
        if self.backend is None:
            try:
                self.backend = open_backend()
            except Exception:
                raise ConnectionError('OPERATOR_VAULT_UNAVAILABLE', 'A protected OS vault is required for operator login.') from None
        client = RemoteOperatorHTTP(origin)
        try:
            client('POST', '/api/v1/operator-auth/login', {'username': username, 'password': password})
            client.username = username.strip()
            me = client.verify()
            if previous and previous['server_id'] != me['server_id']:
                raise ConnectionError('SERVER_ID_MISMATCH', 'This origin now identifies another Server. Use a separate reviewed profile.')
            metadata = dict(format=1, origin=origin, server_id=me['server_id'], username=username.strip())
            # Metadata first: it contains no secret. A vault failure leaves an
            # unauthenticated profile, never a plaintext session fallback.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, metadata)
            self.secret('set', origin, client.token)
        except Exception as error:
            if client.token:
                try:
                    client('POST', '/api/v1/operator-auth/logout')
                except Exception:
                    pass  # Canonical session expiry still bounds this failed login.
            if isinstance(error, ConnectionError) and error.code in ('PROFILE_CONFLICT', 'SERVER_ID_MISMATCH', 'OPERATOR_VAULT_UNAVAILABLE', 'SERVER_UPGRADE_REQUIRED'):
                raise
            raise ConnectionError('OPERATOR_LOGIN_FAILED', 'Operator sign-in could not be completed. Check the Server, account and OS vault.') from None
        return dict(state='authenticated', profile=self.name, **metadata)


class RemoteOperatorHTTP(LocalOperatorHTTP):
    def __init__(self, origin, *, token=None, server_id=None, username=None):
        self.base = server_origin(origin)
        self.token = session_token(token) if token is not None else None
        self.server_id, self.username = server_id, username
        self.timeout, self.max_response_bytes = 30, 8 * 1048576
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request_headers(self):
        result = super().request_headers() | {'Origin': self.base, 'X-Nexus-Operator-Session-Required': '1'}
        if self.token:
            result['Cookie'] = COOKIE + '=' + self.token
        return result

    def receive_headers(self, method, path, response):
        if (method, path) != ('POST', '/api/v1/operator-auth/login'):
            return
        cookies = SimpleCookie()
        try:
            for value in response.headers.get_all('Set-Cookie', []):
                cookies.load(value)
            cookie = cookies[COOKIE]
            if (cookie['domain'] not in ('', urlsplit(self.base).hostname) or cookie['path'] != '/api/v1' or
                    self.base.startswith('https:') and not cookie['secure']):
                raise ValueError()
            self.token = session_token(cookie.value)
        except (KeyError, ValueError):
            raise ConnectionError('OPERATOR_LOGIN_FAILED', 'The Server did not return an origin-bound operator session.') from None

    def __call__(self, method, path, body=None):
        if (not isinstance(path, str) or not path.startswith('/api/v1/') or
                any(part in ('.', '..') for part in path.split('?')[0].split('/')) or
                '#' in path or '\\' in path):
            raise ConnectionError('INVALID_ROUTE', 'Operator requests must remain on the selected Server API origin.')
        try:
            return super().__call__(method, path, body)
        except ConnectionError as error:
            if error.code == 'AUTH_FAILED':
                raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'The operator session expired or was revoked. Sign in again on this operator client.', stage=error.stage) from None
            raise

    def verify(self, *, call=None):
        request = call or self
        status = request('GET', '/api/v1/operator-auth/status')['data']
        if not status.get('session_required_header'):
            raise ConnectionError('SERVER_UPGRADE_REQUIRED', 'Upgrade the Server to support explicit operator-session-only requests.')
        if not status.get('authenticated') or status.get('username') != self.username or not self.username:
            raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in to this Server with a human operator account.')
        me = request('GET', PREFIX + '/connections/me')
        if self.server_id is not None and me['server_id'] != self.server_id:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The operator profile belongs to another Server installation.')
        return me
