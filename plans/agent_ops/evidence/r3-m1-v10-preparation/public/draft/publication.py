"""Best-effort diagnostic publication; critical controller writes stay outside.

Only Windows access/sharing errors (5/32) are retried, with at most 80ms of
retry delay per poll. A stuck operating-system file call has no atomic deadline
guarantee. No provider, private checkpoint or admission policy is changed.
"""
import time

def publish_live(writer, value, diagnostics, *, clock=time.monotonic, sleep=time.sleep):
    started=clock()
    while True:
        diagnostics['attempts']=diagnostics.get('attempts',0)+1
        try:
            writer(value)
        except PermissionError as error:
            code=getattr(error,'winerror',None)
            if code not in (5,32):raise
            diagnostics['windows_publication_errors']=diagnostics.get('windows_publication_errors',0)+1
            diagnostics['last_winerror']=code
            remaining=.08-(clock()-started)
            if remaining<=0:
                diagnostics['deferred_snapshots']=diagnostics.get('deferred_snapshots',0)+1
                return False
            sleep(min(.01,remaining))
        else:
            diagnostics['published_snapshots']=diagnostics.get('published_snapshots',0)+1
            return True

def poll_and_publish(controller,writer,diagnostics,request_id,*,clock=time.monotonic,sleep=time.sleep,wall_time=time.time):
    # Deliberately outside the publication catch: any critical observation or
    # checkpoint failure propagates to the runner's existing fail-closed handler.
    summary=controller.poll()
    publish_live(writer,{'time':wall_time(),'summary':summary,'active_request':request_id},
                 diagnostics,clock=clock,sleep=sleep)
    return summary
