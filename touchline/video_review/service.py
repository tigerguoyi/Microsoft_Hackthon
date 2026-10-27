"""Private local video API. Public/Azure intake stays disabled pending deployment isolation."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import defaultdict,deque
from http.cookies import SimpleCookie
from urllib.parse import urlsplit,parse_qs
from . import storage,jobs
from .project import confirm
from .analysis import analyze,sensitivity
from .counterfactual import simulate

def secret():
    path=storage.ROOT / '.session-key'
    with storage.LOCK:
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            return path.read_bytes()
        with os.fdopen(fd,'wb') as out:out.write(secrets.token_bytes(32))
        return path.read_bytes()

RATES=defaultdict(deque)


def enabled(handler):
    host=handler.headers.get('Host','').split(':')[0]
    peer=getattr(handler,'client_address',('',))[0]
    return (host in ('127.0.0.1','localhost') and peer in ('127.0.0.1','::1') and handler.trusted()
            and not any(os.getenv(x) for x in ('WEBSITE_INSTANCE_ID','WEBSITE_HOSTNAME','NEXTPLAY_PUBLIC_ORIGIN'))
            and os.getenv('NEXTPLAY_VIDEO_ENABLED','1')=='1')


def session(handler,create=False):
    cookie=SimpleCookie()
    try:cookie.load(handler.headers.get('Cookie',''))
    except Exception:pass
    token=cookie.get('nextplay_video_session');token=token.value if token else None
    if token is not None and not re.fullmatch('[a-f0-9]{64}',token):raise ValueError('Invalid private session')
    if token is None:
        if not create:raise PermissionError('Open Video Analysis to create a private local session')
        token=secrets.token_hex(32)
    owner=hmac.new(secret(),token.encode(),hashlib.sha256).hexdigest()
    csrf=hmac.new(secret(),('csrf:'+token).encode(),hashlib.sha256).hexdigest()
    return token,owner,csrf


def gate(handler,post=False):
    if not enabled(handler):raise PermissionError('Video intake is disabled on public/Azure hosts; use the private local workspace')
    token,owner,csrf=session(handler)
    if post and not hmac.compare_digest(handler.headers.get('X-Video-CSRF',''),csrf):raise PermissionError('Missing private video CSRF token')
    return owner


def reply(handler,status,value,cookie=None):
    body=json.dumps(value,ensure_ascii=False,allow_nan=False).encode();handler.send_response(status)
    handler.send_header('Content-Type','application/json');handler.send_header('Content-Length',str(len(body)));handler.send_header('Cache-Control','private, no-store');handler.send_header('X-Content-Type-Options','nosniff')
    if cookie:handler.send_header('Set-Cookie',f'nextplay_video_session={cookie}; HttpOnly; SameSite=Strict; Path=/api/video-review; Max-Age=86400')
    handler.end_headers();handler.wfile.write(body)


def limit(owner,kind,maximum,window):
    now=time.monotonic();key=(owner,kind)
    with storage.LOCK:
        times=RATES[key]
        while times and times[0]<now-window:times.popleft()
        if len(times)>=maximum:raise ValueError('Video request rate limit reached')
        times.append(now)
        if len(RATES)>2048:
            for k in list(RATES):
                if not RATES[k] or RATES[k][-1]<now-3600:del RATES[k]


def media(handler,video_id,owner):
    a=storage.asset(video_id,owner);path=storage.folder(video_id)/'media';size=a['bytes'];start=0;end=size-1;header=handler.headers.get('Range')
    if header:
        m=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
        if not m or not any(m.groups()):raise ValueError('Invalid byte range')
        left,right=m.groups()
        if left:start=int(left);end=min(size-1,int(right)) if right else size-1
        else:start=max(0,size-int(right))
        if start>end or start>=size:handler.send_response(416);handler.send_header('Content-Range',f'bytes */{size}');handler.end_headers();return
    handler.send_response(206 if header else 200);handler.send_header('Content-Type',a['media_type']);handler.send_header('Content-Length',str(end-start+1));handler.send_header('Accept-Ranges','bytes');handler.send_header('Cache-Control','private, no-store');handler.send_header('X-Content-Type-Options','nosniff')
    if header:handler.send_header('Content-Range',f'bytes {start}-{end}/{size}')
    handler.end_headers()
    with path.open('rb') as stream:
        stream.seek(start);remaining=end-start+1
        while remaining:
            block=stream.read(min(65536,remaining))
            if not block:break
            handler.wfile.write(block);remaining-=len(block)


def error(handler,e):
    if isinstance(e,PermissionError):reply(handler,403,dict(error=str(e)))
    elif isinstance(e,FileNotFoundError):reply(handler,404,dict(error='Private video/revision/job not found'))
    elif isinstance(e,(ValueError,KeyError,TypeError,IndexError)):reply(handler,400,dict(error=str(e)[:240] if isinstance(e,ValueError) else 'Invalid versioned video request'))
    else:reply(handler,503,dict(error='Video operation unavailable; decoder or worker failed. Manual annotation remains available after valid upload.'))


def handle_get(handler):
    route=urlsplit(handler.path)
    if not route.path.startswith('/api/video-review/'):return False
    try:
        if route.path=='/api/video-review/config':
            if not enabled(handler):reply(handler,200,dict(enabled=False,reason='Private local video workspace only; public intake is disabled'));return True
            token,owner,csrf=session(handler,True)
            reply(handler,200,dict(enabled=True,csrf=csrf,cv=jobs.capabilities(),max_bytes=storage.MAX_BYTES,max_duration_s=120,retention_days=int(os.getenv('NEXTPLAY_VIDEO_RETENTION_DAYS','7'))),cookie=token);return True
        owner=gate(handler);q=parse_qs(route.query)
        if route.path.startswith('/api/video-review/media/'):media(handler,route.path.rsplit('/',1)[1],owner)
        elif route.path=='/api/video-review/revision':reply(handler,200,storage.revision(q['video_id'][0],q['revision_id'][0],owner,current=False))
        elif route.path.startswith('/api/video-review/jobs/'):
            reply(handler,200,jobs.status(q['video_id'][0],route.path.rsplit('/',1)[1],owner))
        elif route.path=='/api/video-review/assets':
            values=[]
            for path in storage.ROOT.glob('*/asset.json'):
                a=storage.read(path)
                if a['owner']==owner:values.append({k:v for k,v in a.items() if k!='owner'})
            reply(handler,200,dict(videos=values))
        else:reply(handler,404,dict(error='Unknown private video route'))
    except Exception as e:error(handler,e)
    return True


def handle_upload(handler):
    if urlsplit(handler.path).path!='/api/video-review/upload':return False
    try:
        owner=gate(handler,True);limit(owner,'upload',5,60)
        if handler.headers.get('X-Video-Rights')!='confirmed':raise ValueError('Confirm permission to use this video before upload')
        size=int(handler.headers.get('Content-Length','0'));connection=getattr(handler,'connection',None);old=connection.gettimeout() if connection else None
        if connection:connection.settimeout(30)
        try:value=storage.upload(handler.rfile,size,handler.headers.get('Content-Type',''),owner)
        finally:
            if connection:connection.settimeout(old)
        reply(handler,201,value)
    except Exception as e:error(handler,e)
    return True


def handle_post(handler,route,data):
    if not route.startswith('/api/video-review/'):return False
    try:
        owner=gate(handler,True)
        if route=='/api/video-review/confirm':
            if set(data)!={'annotation'}:raise ValueError('Expected annotation only')
            reply(handler,200,confirm(data['annotation']['video_id'],data['annotation'],owner))
        elif route in ('/api/video-review/analyze','/api/video-review/partial-context','/api/video-review/candidates'):reply(handler,200,analyze(data,owner))
        elif route=='/api/video-review/sensitivity':reply(handler,200,sensitivity(data,owner))
        elif route=='/api/video-review/counterfactual':reply(handler,200,simulate(data,owner))
        elif route=='/api/video-review/detect':
            if set(data)!={'video_id','timestamps'}:raise ValueError('Expected video and timestamps')
            limit(owner,'detect',3,60);reply(handler,202,jobs.submit(data['video_id'],data['timestamps'],owner))
        elif route=='/api/video-review/delete':
            if set(data)!={'video_id'}:raise ValueError('Expected video ID')
            storage.remove(data['video_id'],owner);reply(handler,200,dict(deleted=True))
        elif route=='/api/video-review/agents':
            from .agents import run,VideoEvidenceAdapter
            from server import read_config,claim_model_call
            adapter=VideoEvidenceAdapter(data['selection'],owner)
            for key in ('snapshot_id','candidate_set_id','analysis_id'):
                if data[key]!=adapter.result[key]:raise ValueError('Stale Agent selection')
            limit(owner,'agents',10,3600);config=read_config()
            if config.get('api_key') and config.get('model') and not claim_model_call():config={}
            reply(handler,200,run(data,owner,config))
        else:reply(handler,404,dict(error='Unknown private video route'))
    except Exception as e:error(handler,e)
    return True
