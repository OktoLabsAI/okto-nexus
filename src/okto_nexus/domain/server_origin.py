"""Pure normalization of an explicit operator Server origin."""
from urllib.parse import urlsplit


def normalize_server_origin(value):
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
        raise ValueError('Invalid Server origin.') from None
