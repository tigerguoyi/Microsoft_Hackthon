"""Isolated optional CV process. It cannot access model API credentials."""
import os
import sys
import signal
from pathlib import Path
from .storage import read,write,folder


def run(video_id,job_id):
    if hasattr(signal,'alarm'):signal.alarm(290)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
    from demo.observations import extract_observations
    root=Path(os.environ['NEXTPLAY_VIDEO_JOB_ROOT']);target=folder(video_id,root)/('job-'+job_id+'.json');job=read(target)
    try:
        job.update(status='running');write(target,job)
        def progress(value):
            job['progress']=value;write(target,job)
        result=extract_observations(folder(video_id,root)/'media',job['timestamps'],job,progress)
        job.update(status='complete',progress=1.,result=result);write(target,job)
    except Exception as e:
        job.update(status='failed',error=type(e).__name__+': '+str(e)[:240]);write(target,job)


if __name__=='__main__':run(sys.argv[1],sys.argv[2])
