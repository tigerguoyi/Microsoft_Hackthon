"""One bounded external CV worker; web requests never run YOLO inference."""
import os
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from . import storage
from .storage import asset, folder, read, write, LOCK


def capabilities():
    import sys
    src=str(Path(__file__).resolve().parents[2]/'src')
    if src not in sys.path:sys.path.insert(0,src)
    from demo.observations import available
    models=os.getenv('NEXTPLAY_VIDEO_MODELS',str(Path(__file__).resolve().parents[2]/'data/models'))
    return dict(**available(models),models_dir=models,worker='bounded_local_subprocess',max_jobs=1,timeout_s=300)


def submit(video_id,timestamps,owner,root=None):
    root=Path(root or storage.ROOT);a=asset(video_id,owner,root)
    if not isinstance(timestamps,list) or not 1<=len(timestamps)<=60 or any(type(t) is not int or not 0<=t<a['duration_ms'] for t in timestamps):
        raise ValueError('Choose 1–60 in-range video timestamps')
    caps=capabilities()
    if not caps['available']:raise ValueError('Automatic detection unavailable; install optional CV dependencies/local football weights or use manual annotation')
    jid=uuid.uuid4().hex;path=folder(video_id,root)/('job-'+jid+'.json');lock=root/'cv-worker.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        # Never run competing Torch workers. Operator can remove a crash-stale lock after 310s.
        if time.time()-lock.stat().st_mtime>310:lock.unlink(missing_ok=True);return submit(video_id,timestamps,owner,root)
        raise ValueError('CV worker busy; wait for the existing job')
    os.close(fd)
    record=dict(job_id=jid,video_id=video_id,status='queued',progress=0.,created_at=time.time(),timestamps=timestamps,models_dir=caps['models_dir'],timeout_s=240)
    write(path,record)
    env={k:v for k,v in os.environ.items() if not any(secret in k for secret in ('API_KEY','TOKEN','PASSWORD'))};env['NEXTPLAY_VIDEO_JOB_ROOT']=str(root);env['YOLO_AUTOINSTALL']='False'
    try:
        proc=subprocess.Popen([os.sys.executable,'-m','video_review.worker',video_id,jid],cwd=Path(__file__).resolve().parents[1],env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception:
        lock.unlink(missing_ok=True);record.update(status='failed',error='Worker startup failed');write(path,record);raise
    def monitor():
        try:proc.wait(timeout=300)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        finally:
            value=read(path)
            if value['status'] in ('running','queued'):value.update(status='failed',error='Worker exited or timed out before completion');write(path,value)
            lock.unlink(missing_ok=True)
    threading.Thread(target=monitor,daemon=True).start()
    return record


def status(video_id,job_id,owner,root=None):
    asset(video_id,owner,root)
    import re
    if not isinstance(job_id,str) or not re.fullmatch('[a-f0-9]{32}',job_id):raise ValueError('Invalid job ID')
    result=read(folder(video_id,root)/('job-'+job_id+'.json'))
    if result['status'] in ('queued','running') and time.time()-result['created_at']>310:
        result.update(status='failed',error='Worker expired; submit a new detection task')
        write(folder(video_id,root)/('job-'+job_id+'.json'),result)
    return result
