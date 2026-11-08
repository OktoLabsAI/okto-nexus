"""Bounded read-only M1 host observations, never transcript reads or auth grants.

This is specific to both M1 lanes sharing this machine. The canonical Server DB
resolves the exact reserved intent independently of an in-flight HTTP response;
the selected Core journal supplies a private usage projection, not a claim that
Server event publication or provider billing has caught up.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import sqlite3
import time

import token_collector as tokens


class JournalUnknown(ValueError):
    pass


def require(value, reason):
    if not value:
        raise JournalUnknown(reason)


def safe_path(path, root):
    path, root = Path(path), Path(root).resolve()
    require(path.resolve().is_relative_to(root), 'PATH_OUTSIDE_CAMPAIGN')
    for item in (path, *path.parents):
        if item == root.parent:
            break
        require(not item.is_symlink() and not item.is_junction(), 'PATH_LINK')
    return path.resolve()


class ReadOnly:
    def __init__(self, root, *, sql_budget=.04):
        require(0 < sql_budget <= .1, 'SQL_BUDGET_INVALID')
        self.root, self.budget = Path(root).resolve(), sql_budget
        self.identities = {}

    @contextmanager
    def open(self, path):
        path = safe_path(path, self.root)
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        require(self.identities.setdefault(str(path), identity) == identity, 'DATABASE_REPLACED')
        started = time.monotonic()
        db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=self.budget)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA busy_timeout='+str(int(self.budget*1000)))
            db.set_progress_handler(lambda: int(time.monotonic()-started >= self.budget), 200)
            db.execute('BEGIN')
            yield db
            require(time.monotonic()-started <= self.budget*2, 'READ_BUDGET_EXCEEDED')
        finally:
            db.close()
        after = path.stat()
        require((after.st_dev, after.st_ino) == identity, 'DATABASE_REPLACED')


class CanonicalIntentReader:
    def __init__(self, root, server_home, *, server_id, actor_id, pre_scope):
        self.io = ReadOnly(root)
        self.database = safe_path(Path(server_home)/'nexus.db', root)
        self.server_id, self.actor_id = server_id, actor_id
        require(set(pre_scope) == set(tokens.PRE_SCOPE), 'PRE_SCOPE_INVALID')
        require(pre_scope['server_id'] == server_id, 'SERVER_MISMATCH')
        self.pre_scope = dict(pre_scope)
        self.known = {}

    def read(self, request_id):
        tokens.identifier(request_id)
        with self.io.open(self.database) as db:
            rows = db.execute("SELECT operation_id,json_extract(resolved_json,'$.client_intent_id') AS intent,"
                "json_extract(resolved_json,'$.scope') AS scope,json_extract(initial_turn_json,'$.operation_id') AS initial_turn "
                "FROM execution_client_intents WHERE server_id=? AND actor_agent_id=? AND client_intent_id=? LIMIT 2",
                (self.server_id,self.actor_id,request_id)).fetchall()
            require(len(rows) <= 1, 'INTENT_AMBIGUOUS')
            if not rows:
                require(request_id not in self.known, 'INTENT_ROLLBACK')
                return None
            row = rows[0]
            require(row['intent'] == request_id, 'INTENT_MISMATCH')
            raw_scope = json.loads(row['scope'])
            require(all(raw_scope.get(k) == v for k,v in self.pre_scope.items()), 'INTENT_SCOPE_MISMATCH')
            scope = {k:raw_scope[k] for k in (*tokens.IDS,*tokens.REVISIONS)}
            for key in tokens.IDS:tokens.identifier(scope[key])
            for key in tokens.REVISIONS:tokens.number(scope[key])
            opening_id, operation_id = row['operation_id'], row['initial_turn'] or row['operation_id']
            tokens.identifier(opening_id); tokens.identifier(operation_id)
            stable = dict(scope=scope, opening_operation_id=opening_id, operation_id=operation_id)
            require(self.known.setdefault(request_id, stable) == stable, 'INTENT_REBOUND')
            session = db.execute("SELECT binding_id,workspace_id,workspace_binding_id,owner_generation,"
                "open_operation_id,lifecycle_state,lease_state,stream_epoch FROM execution_sessions "
                "WHERE server_id=? AND executor_id=? AND session_id=?",
                (scope['server_id'],scope['executor_id'],scope['session_id'])).fetchone()
            if session is not None:
                require(all(session[k] == scope[k] for k in ('binding_id','workspace_id','workspace_binding_id'))
                    and session['owner_generation'] == scope['session_owner_generation'], 'SESSION_SCOPE_MISMATCH')
            def receipt(op):
                found=db.execute("SELECT stage,error_code,possible_effect,retry_safe,receipt_revision FROM execution_receipts "
                    "WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1",
                    (scope['server_id'],scope['executor_id'],op)).fetchone()
                return dict(found) if found else None
            parent, turn = receipt(opening_id), receipt(operation_id)
            operation = db.execute("SELECT subject_agent_id,binding_id,workspace_id,workspace_binding_id,session_id,"
                "admission_state,action FROM execution_operations WHERE server_id=? AND executor_id=? AND operation_id=?",
                (scope['server_id'],scope['executor_id'],operation_id)).fetchone()
            if operation is not None:
                require(operation['subject_agent_id']==scope['agent_id'] and all(operation[k]==scope[k]
                    for k in ('binding_id','workspace_id','workspace_binding_id','session_id')), 'OPERATION_SCOPE_MISMATCH')
            failed = bool(parent and parent['stage']=='FAILED' and parent['error_code']=='PREPARATION_FAILED'
                and parent['possible_effect']==0 and session and session['stream_epoch'] is None)
            return stable | {'session_state':dict(session) if session else None,
                'operation_receipt':turn,'opening_receipt':parent,'preopen_failed':failed,
                'operation_admitted':operation is not None,
                'source':'OWN_CANONICAL_DB_READ_ONLY','billed_tokens':None}


class CoreJournalReader:
    def __init__(self, root, owner_home, lane):
        require(lane in ('local','connector'), 'LANE_INVALID')
        self.io = ReadOnly(root)
        self.owner = safe_path(owner_home, root)
        self.lane = lane
        self.epochs = {}
        self.watermarks = {}
        self.seen_paths = set()

    def path(self, scope):
        if self.lane == 'connector':
            return safe_path(self.owner/'executor-journal.db',self.io.root)
        digest=hashlib.sha256((scope['executor_id']+'\0'+scope['session_id']).encode('ascii')).hexdigest()
        return safe_path(self.owner/'core-runtime'/('session-'+digest+'.db'),self.io.root)

    def read(self, scope, after=0):
        path=self.path(scope)
        key=tuple(scope[k] for k in ('server_id','executor_id','session_id'))
        if not path.exists():
            require(str(path) not in self.seen_paths, 'JOURNAL_DISAPPEARED')
            return None
        self.seen_paths.add(str(path))
        with self.io.open(path) as db:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'events','event_streams'} <= tables:
                require(key not in self.epochs, 'JOURNAL_SCHEMA_ROLLBACK')
                return None
            streams=db.execute('SELECT stream_epoch,next_sequence,compacted_sequence FROM event_streams '
                'WHERE server_id=? AND executor_id=? AND session_id=? LIMIT 2',key).fetchall()
            require(len(streams)<=1, 'MULTIPLE_SESSION_EPOCHS')
            if not streams:
                require(key not in self.epochs,'STREAM_ROLLBACK')
                return None
            epoch, next_sequence, compacted=streams[0]
            tokens.identifier(epoch)
            require(self.epochs.setdefault(key,epoch)==epoch,'EPOCH_CHANGED')
            watermark=next_sequence-1
            require(compacted<=after<=watermark,'EVENT_GAP_OR_CURSOR_ROLLBACK')
            require(watermark>=self.watermarks.get(key,0),'WATERMARK_ROLLBACK')
            self.watermarks[key]=watermark
            selectors=['sequence',"json_extract(body,'$.server_id') AS body_server", "json_extract(body,'$.executor_id') AS body_executor",
                "json_extract(body,'$.session_id') AS body_session", "json_extract(body,'$.stream_epoch') AS body_epoch",
                "json_extract(body,'$.category') AS category", "json_extract(body,'$.native_type') AS native_type",
                "json_extract(body,'$.operation_id') AS operation_id"]
            fields={'thread_id':'thread_id','threadId':'threadId','turn_id':'turn_id','turnId':'turnId',
                'turn_name':'turn.id','turn_status':'turn.status','phase':'delivery_phase','outcome':'delivery_outcome',
                'window':'tokenUsage.modelContextWindow'}
            for alias,json_path in fields.items():
                selectors.append("json_extract(body,'$.payload."+json_path+"') AS "+alias)
            for group in ('total','last'):
                for counter in (*tokens.COUNTERS,'cacheWriteInputTokens'):
                    alias=group+'_'+counter
                    suffix='$.payload.tokenUsage.'+group+'.'+counter
                    selectors.extend(["json_extract(body,'"+suffix+"') AS "+alias,
                                      "json_type(body,'"+suffix+"') AS "+alias+'_type'])
            rows=db.execute('SELECT '+','.join(selectors)+' FROM events WHERE server_id=? AND executor_id=? '
                'AND session_id=? AND stream_epoch=? AND sequence>? AND sequence<=? ORDER BY sequence LIMIT 500',
                (*key,epoch,after,watermark)).fetchall()
            events=[]
            for expected,row in enumerate(rows,after+1):
                require(row['sequence']==expected,'EVENT_GAP')
                require((row['body_server'],row['body_executor'],row['body_session'],row['body_epoch'])==(*key,epoch),'EVENT_SCOPE_MISMATCH')
                kind=row['native_type']
                # Unknown events advance sequence using an inert metadata projection.
                # No output, command, tool input/result or arbitrary payload is selected.
                known=kind in ('turn/started','turn/completed','thread/tokenUsage/updated')
                value=dict(server_id=key[0],executor_id=key[1],session_id=key[2],stream_epoch=epoch,
                    sequence=expected,category=row['category'] if known else 'other',native_type=kind if known else None,
                    operation_id=row['operation_id'] if known else None,payload={})
                if known:
                    payload={k:row[k] for k in ('thread_id','threadId','turn_id')}
                    if kind=='thread/tokenUsage/updated':
                        payload['turnId']=row['turnId']
                        usage={'modelContextWindow':row['window']}
                        for group in ('total','last'):
                            counters={}
                            for counter in (*tokens.COUNTERS,'cacheWriteInputTokens'):
                                alias=group+'_'+counter
                                if counter=='cacheWriteInputTokens' and row[alias+'_type'] is None:continue
                                require(row[alias+'_type']=='integer','USAGE_COUNTER_TYPE')
                                counters[counter]=row[alias]
                            usage[group]=counters
                        payload['tokenUsage']=usage
                    else:
                        payload.update(turn={'id':row['turn_name'],'status':row['turn_status']},
                            delivery_phase=row['phase'],delivery_outcome=row['outcome'])
                    value['payload']=payload
                elif kind in ('thread/started','core/codex_thread_configuration') and row['thread_id'] is not None:
                    tokens.identifier(row['thread_id'])
                    value['payload']={'thread_id':row['thread_id']}
                events.append(value)
            require(events or after==watermark,'EVENT_GAP')
            cursor=after+len(events)
            return {'scope':dict(scope),'stream_epoch':epoch,'events':events,'count':len(events),
                'next_after_sequence':cursor,'committed_contiguous':watermark,'gap_pending':False,'has_more':cursor<watermark}
