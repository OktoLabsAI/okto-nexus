"""Own ASGI boundary: real app responses, optional delay, no DTO fabrication."""
import asyncio


class BrowserSurface:
    def __init__(self,app,*,record,delay_info_seconds=0,allow_native_decision=False):
        assert 0<=delay_info_seconds<=15
        self.app,self.record=app,record
        self.delay=delay_info_seconds
        self.first_info=True
        self.allow_native_decision=allow_native_decision
        self.decision_posts=0

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        method,path=scope['method'],scope['path']
        scope=dict(scope)
        # Official opt-in prevents loopback from bypassing this own human session.
        scope['headers']=[(k,v) for k,v in scope['headers'] if k.lower()!=b'x-nexus-operator-session-required']+[(b'x-nexus-operator-session-required',b'1')]
        item=dict(method=method,path=path)
        self.record(item)
        async def logged(message):
            if message['type']=='http.response.start':item['status']=message['status']
            await send(message)
        decision=self.allow_native_decision and method=='POST' and path=='/api/v1/runtime-management/runtime/approval-decisions' and self.decision_posts<2
        if decision:self.decision_posts+=1
        allowed=method in ('GET','HEAD','OPTIONS') or decision
        if not allowed:
            from starlette.responses import JSONResponse
            return await JSONResponse({'fixture':'Write not allowed'},status_code=405)(scope,receive,logged)
        if path=='/api/v1/info' and self.first_info:
            self.first_info=False
            item['controlled_delay_seconds']=self.delay
            await asyncio.sleep(self.delay)
        return await self.app(scope,receive,logged)
