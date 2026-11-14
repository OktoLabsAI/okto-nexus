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
import threading

import token_collector as tokens


class JournalUnknown(ValueError):
    pass


def require(value, reason):
    if not value:
        raise JournalUnknown(reason)


def reader_error_metadata(error):
    value=getattr(error,'m1_reader_diagnostic',None)
    if type(value) is not dict or value.get('phase') not in ('schema_initialization','snapshot_read'):return None
    if any(type(value.get(key)) not in (int,float) or not 0<=value[key]<1e12 for key in ('budget_ms','elapsed_ms')):return None
    return {key:value[key] for key in ('phase','budget_ms','elapsed_ms')}


def safe_path(path, root):
    path, root = Path(path), Path(root).resolve()
    require(path.resolve().is_relative_to(root), 'PATH_OUTSIDE_CAMPAIGN')
    for item in (path, *path.parents):
        if item == root.parent:
            break
        require(not item.is_symlink() and not item.is_junction(), 'PATH_LINK')
    return path.resolve()


class ReadOnly:
    def __init__(self, root, *, sql_budget=.1, initialization_budget=.25, clock=time.monotonic):
        require(0 < sql_budget <= .1, 'SQL_BUDGET_INVALID')
        require(0 < initialization_budget <= .25, 'INITIALIZATION_BUDGET_INVALID')
        self.root, self.budget = Path(root).resolve(), sql_budget
        self.initialization_budget=initialization_budget;self.clock=clock
        self.owner=threading.get_ident();self.connections={};self.initializations=[]
        self.closed=False;self.failed=False;self.close_error_types=[];self.schema_changes=[]
        self.identities = {}
        self.aggregate_check=None

    def check_aggregate(self):
        if self.aggregate_check is not None:self.aggregate_check()

    def observe(self,action):
        started=self.clock();before=len(self.initializations)
        value=action()
        initialization=sum(item['elapsed_ms']/1000 for item in self.initializations[before:])
        self.check_aggregate()
        elapsed=self.clock()-started-initialization
        if elapsed>=self.budget:
            error=JournalUnknown('READ_BUDGET_EXCEEDED')
            error.m1_reader_diagnostic={'phase':'snapshot_read','budget_ms':self.budget*1000,'elapsed_ms':elapsed*1000}
            self.failed=True;self._release()
            raise error
        return value

    def _progress(self,started,budget,aggregate_errors):
        def check():
            try:self.check_aggregate()
            except BaseException as error:
                aggregate_errors.append(error)
                return 1
            return int(self.clock()-started>=budget)
        return check

    def _owned(self):
        require(threading.get_ident()==self.owner,'READER_OWNER_CHANGED')

    def _release(self):
        entries,self.connections=self.connections,{}
        for entry in entries.values():
            self._dispose(entry['db'])

    def _dispose(self,db):
        try:db.set_progress_handler(None,0);db.rollback()
        except BaseException as error:self.close_error_types.append(type(error).__name__)
        finally:
            try:db.close()
            except BaseException as error:self.close_error_types.append(type(error).__name__)

    def close(self):
        self._owned()
        self.closed=True
        self._release()

    def diagnostics(self):
        self._owned()
        return {'closed':self.closed,'failed':self.failed,'open_connections':len(self.connections),
                'close_error_types':list(self.close_error_types),
                'schema_changes':[dict(item) for item in self.schema_changes],
                'read_budget_ms':self.budget*1000,'initialization_budget_ms':self.initialization_budget*1000,
                'initializations':[dict(item) for item in self.initializations]}

    def _identity(self,path):
        safe_path(path,self.root)
        stat=path.stat();identity=(stat.st_dev,stat.st_ino)
        require(self.identities.setdefault(str(path),identity)==identity,'DATABASE_REPLACED')
        return identity

    def prepare(self,path):
        """One bounded schema initialization; no work/admission and no retained snapshot."""
        self._owned()
        require(not self.closed,'READER_CLOSED');require(not self.failed,'READER_FAILED')
        db=None;started=self.clock();path_name=Path(path).name;aggregate_errors=[]
        try:
            self.check_aggregate()
            path=safe_path(path,self.root);identity=self._identity(path)
            if str(path) in self.connections:return self.connections[str(path)]
            require(len(self.connections)<8,'READER_CONNECTION_LIMIT')
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=self.budget)
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA busy_timeout='+str(int(self.budget*1000)))
            db.set_progress_handler(self._progress(started,self.initialization_budget,aggregate_errors),200)
            # Schema loading is explicit and bounded separately from each100ms
            # observation. The query projects a count, never arbitrary SQL/body.
            db.execute('SELECT count(*) FROM sqlite_schema').fetchone()
            schema_version=db.execute('PRAGMA schema_version').fetchone()[0]
            require(self._identity(path)==identity,'DATABASE_REPLACED')
            db.set_progress_handler(None,0);db.rollback()
            require(not db.in_transaction,'SNAPSHOT_NOT_RELEASED')
            elapsed=self.clock()-started
            self.check_aggregate()
            require(elapsed<self.initialization_budget,'INITIALIZATION_BUDGET_EXCEEDED')
            entry={'db':db,'identity':identity,'schema_version':schema_version}
            self.connections[str(path)]=entry;db=None
            self.initializations.append({'file_name':path_name,'elapsed_ms':elapsed*1000,
                                         'budget_ms':self.initialization_budget*1000,'status':'PREPARED'})
            return entry
        except BaseException as error:
            if aggregate_errors:error=aggregate_errors[0]
            self.failed=not getattr(error,'aggregate_only',False)
            elapsed_ms=(self.clock()-started)*1000
            error.m1_reader_diagnostic={'phase':'schema_initialization','budget_ms':self.initialization_budget*1000,'elapsed_ms':elapsed_ms}
            self.initializations.append({'file_name':path_name,'elapsed_ms':elapsed_ms,
                                         'budget_ms':self.initialization_budget*1000,'status':'FAILED',
                                         'error_type':type(error).__name__})
            if db is not None:
                self._dispose(db)
            if self.failed:self._release()
            raise error

    @contextmanager
    def open(self, path):
        # An initial schema load has its own250ms budget. Cached validation,
        # path resolution, snapshot projection and rollback share one100ms clock.
        started=self.clock();initializations=len(self.initializations)
        entry=self.prepare(path)
        if len(self.initializations)!=initializations:started=self.clock()
        db=entry['db'];primary=None;aggregate_errors=[];cleanup_failed=False
        try:
            try:
                path=Path(path).resolve();self._identity(path);self.check_aggregate()
                require(not db.in_transaction,'SNAPSHOT_ALREADY_ACTIVE')
                db.set_progress_handler(self._progress(started,self.budget,aggregate_errors),200)
                db.execute('BEGIN')
                schema_version=db.execute('PRAGMA schema_version').fetchone()[0]
                if schema_version!=entry['schema_version']:
                    self.schema_changes.append({'file_name':path.name,'previous':entry['schema_version'],'current':schema_version})
                    self.schema_changes=self.schema_changes[-16:]
                    entry['schema_version']=schema_version
                yield db
                self._identity(path)
            except BaseException as failure:
                primary=failure
                raise
            finally:
                try:db.set_progress_handler(None,0);db.rollback()
                except BaseException as failure:
                    cleanup_failed=True
                    self.close_error_types.append(type(failure).__name__)
                    if primary is None:raise
            self.check_aggregate()
            require(self.clock()-started<self.budget,'READ_BUDGET_EXCEEDED')
        except BaseException as failure:
            if aggregate_errors:failure=aggregate_errors[0]
            self.failed=cleanup_failed or not getattr(failure,'aggregate_only',False)
            failure.m1_reader_diagnostic={'phase':'snapshot_read','budget_ms':self.budget*1000,
                                         'elapsed_ms':(self.clock()-started)*1000}
            if self.failed:self._release()
            raise failure


class CanonicalIntentReader:
    def __init__(self, root, server_home, *, server_id, actor_id, pre_scope):
        self.io = ReadOnly(root)
        self.database = safe_path(Path(server_home)/'nexus.db', root)
        self.server_id, self.actor_id = server_id, actor_id
        require(set(pre_scope) == set(tokens.PRE_SCOPE), 'PRE_SCOPE_INVALID')
        require(pre_scope['server_id'] == server_id, 'SERVER_MISMATCH')
        self.pre_scope = dict(pre_scope)
        self.known = {}
        self.io.prepare(self.database)  # pre-admission schema preparation

    def close(self):self.io.close()

    def read(self, request_id):
        return self.io.observe(lambda:self._read(request_id))

    def _read(self, request_id):
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

    def close(self):self.io.close()

    def path(self, scope):
        if self.lane == 'connector':
            return safe_path(self.owner/'executor-journal.db',self.io.root)
        digest=hashlib.sha256((scope['executor_id']+'\0'+scope['session_id']).encode('ascii')).hexdigest()
        return safe_path(self.owner/'core-runtime'/('session-'+digest+'.db'),self.io.root)

    def read(self, scope, after=0):
        return self.io.observe(lambda:self._read(scope,after))

    def _read(self, scope, after=0):
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
