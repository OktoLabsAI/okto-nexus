"""Human dashboard credentials and sessions, independent of agent API keys."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

COOKIE = "nexus_operator_session"
SESSION_SECONDS = 8 * 60 * 60


class OperatorAuth:
    def __init__(self, home: Path):
        self.path = Path(home) / "operator-auth.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    salt TEXT NOT NULL, digest TEXT NOT NULL,
                    failures INTEGER NOT NULL DEFAULT 0, blocked_until REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, at REAL NOT NULL, username TEXT NOT NULL,
                    action TEXT NOT NULL, path TEXT NOT NULL, status INTEGER NOT NULL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()

    def configured(self):
        with self.db() as db:
            return db.execute("SELECT 1 FROM account").fetchone() is not None

    def configure(self, username, password, *, local=False, current_password=""):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            account = db.execute("SELECT * FROM account WHERE id=1").fetchone()
            if not local and (not account or not hmac.compare_digest(
                    self.password_hash(current_password, account['salt']), account['digest'])):
                return False
            salt = secrets.token_hex(32)
            db.execute("INSERT OR REPLACE INTO account(id,username,salt,digest) VALUES(1,?,?,?)",
                       (username, salt, self.password_hash(password, salt)))
            db.execute("DELETE FROM sessions")
        self.audit(username, "password_changed", "", 200)
        return True

    def login(self, username, password):
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            account = db.execute("SELECT * FROM account WHERE id=1").fetchone()
            if not account:
                return None
            if account['blocked_until'] > now:
                return None
            valid = hmac.compare_digest(self.password_hash(password, account['salt']), account['digest'])
            if not valid or not hmac.compare_digest(username.encode(), account['username'].encode()):
                failures = account['failures'] + 1
                db.execute("UPDATE account SET failures=?,blocked_until=? WHERE id=1",
                           (0 if failures >= 5 else failures, now + 60 if failures >= 5 else 0))
                return None
            db.execute("UPDATE account SET failures=0,blocked_until=0 WHERE id=1")
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            db.execute("DELETE FROM sessions WHERE digest IN (SELECT digest FROM sessions ORDER BY expires DESC LIMIT -1 OFFSET 99)")
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES(?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), username, now + SESSION_SECONDS))
        self.audit(username, "login", "", 200)
        return token

    def resolve(self, token):
        if not token or len(token) > 128:
            return None
        with self.db() as db:
            row = db.execute("SELECT username FROM sessions WHERE digest=? AND expires>?",
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return row['username'] if row else None

    def logout(self, token):
        username = self.resolve(token)
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256((token or '').encode()).hexdigest(),))
        if username:
            self.audit(username, "logout", "", 200)

    def audit(self, username, action, path, status):
        with self.db() as db:
            db.execute("INSERT INTO audit(at,username,action,path,status) VALUES(?,?,?,?,?)",
                       (time.time(), username, action, path, status))
            db.execute("DELETE FROM audit WHERE id < (SELECT COALESCE(MAX(id),0)-10000 FROM audit)")


def local_operator_request(request):
    from .app import _LOOPBACK_CLIENTS, _loopback_trust_ok
    return bool(request.client and request.client.host in _LOOPBACK_CLIENTS
                and getattr(request.app.state, 'local_open', True)
                and not any(h in request.headers for h in ('forwarded', 'x-forwarded-for', 'x-forwarded-host'))
                and _loopback_trust_ok(request))


def same_origin_request(request):
    origin = request.headers.get('origin')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return False
    if origin:
        try:
            parsed = urlsplit(origin)
            if (parsed.scheme, parsed.netloc) != (request.url.scheme, request.url.netloc):
                return False
        except ValueError:
            return False
    return request.method in ('GET', 'HEAD', 'OPTIONS') or request.headers.get('x-nexus-ui') == '1'


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class AccountInput(LoginInput):
    password: str = Field(min_length=12, max_length=1024)
    current_password: str = Field(default='', max_length=1024)


def router():
    from .app import ok, err
    routes = APIRouter(prefix='/api/v1/operator-auth')

    @routes.get('/status')
    def status(request: Request):
        auth = request.app.state.operator_auth
        local = local_operator_request(request)
        username = auth.resolve(request.cookies.get(COOKIE)) if same_origin_request(request) else None
        response = ok(dict(configured=auth.configured(), local=local,
                           authenticated=bool(local or username), username=username))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @routes.post('/login')
    def login(body: LoginInput, request: Request):
        if not same_origin_request(request):
            return err(403, 'CROSS_ORIGIN_BLOCKED', 'Sign in from the Nexus dashboard.')
        token = request.app.state.operator_auth.login(body.username.strip(), body.password)
        if token is None:
            return err(401, 'AUTH_FAILED', 'Sign-in failed. Check your credentials or try again later.')
        response = ok(dict(authenticated=True))
        response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', path='/api/v1', max_age=SESSION_SECONDS)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @routes.post('/logout')
    def logout(request: Request):
        if not same_origin_request(request):
            return err(403, 'CROSS_ORIGIN_BLOCKED', 'Sign out from the Nexus dashboard.')
        request.app.state.operator_auth.logout(request.cookies.get(COOKIE))
        response = ok(dict(authenticated=False))
        response.delete_cookie(COOKIE, path='/api/v1')
        return response

    @routes.post('/account')
    def account(body: AccountInput, request: Request):
        auth = request.app.state.operator_auth
        local = local_operator_request(request)
        if not same_origin_request(request) or not (local or auth.resolve(request.cookies.get(COOKIE))):
            return err(403, 'PERMISSION_DENIED', 'Configure operator access locally or sign in as the operator.')
        username = body.username.strip()
        if not username:
            return err(422, 'VALIDATION_ERROR', 'Username is required.')
        if not auth.configure(username, body.password, local=local, current_password=body.current_password):
            return err(403, 'AUTH_FAILED', 'The current password is incorrect.')
        response = ok(dict(configured=True))
        response.delete_cookie(COOKIE, path='/api/v1')
        return response

    return routes
