"""Explicit finite read-window extension. Has no product/authority imports."""
import hashlib
import json

class ObservationWindow:
    def __init__(self,started,seconds):
        if type(seconds)is not int or not 60<=seconds<=3600:raise ValueError('initial60..3600seconds')
        self.deadline=started+seconds;self.ceiling=started+7200;self.seen=set();self.last_bytes=None

    def expired(self,now):return now>=self.deadline

    def consume(self,path,now):
        if not path.is_file():return None
        try:raw=path.read_bytes()
        except OSError:return None
        fingerprint=hashlib.sha256(raw).hexdigest()
        if fingerprint==self.last_bytes:return None
        self.last_bytes=fingerprint
        try:
            value=json.loads(raw)
            if type(value)is not dict or set(value)!={'request_id','seconds'}:raise ValueError('shape')
            identity,seconds=value['request_id'],value['seconds']
            if type(identity)is not str or not 1<=len(identity)<=80 or not identity.isprintable():raise ValueError('identity')
            if type(seconds)is not int or not 1<=seconds<=3600:raise ValueError('seconds')
            if identity in self.seen:return {'status':'IGNORED_DUPLICATE','request_id':identity}
            if len(self.seen)>=64:raise ValueError('extension count')
            if self.expired(now):raise ValueError('window already expired')
            self.seen.add(identity)
            self.deadline=min(self.ceiling,max(self.deadline,now)+seconds)
            return {'status':'EXTENDED_READ_WINDOW_ONLY','request_id':identity,'remaining_seconds':max(0,self.deadline-now),'ceiling_seconds_from_start':7200}
        except (ValueError,TypeError,UnicodeError):return {'status':'REJECTED_READ_WINDOW_EXTENSION','reason':'Invalid, expired or out-of-bounds request; original authority is unaffected'}
