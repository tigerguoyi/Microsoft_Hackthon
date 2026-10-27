"""YOLO + ByteTrack observations only: no action classifier or Softmax import.

Reuses project tracking, colour, possession and geometry helpers. All outputs are
automatic preannotations. No image coordinate is silently treated as metres.
"""
from pathlib import Path
import math
import time

from demo.tracking import TrackState
from demo.teams import TeamBook, summarize_jersey
from demo.possessor import PossessorTracker, PlayerFix
from demo.geometry import pitch_vertices_m, assess_homography, invert_homography, apply_homography, scene_cut
from demo.weights import HF_MODELS

VERSION = 'cv-observations-1'


def available(models_dir):
    import importlib.util
    dependencies={name:importlib.util.find_spec(name) is not None for name in ('cv2','torch','ultralytics','lap')}
    weights={k:(Path(models_dir)/v[0]).is_file() for k,v in HF_MODELS.items()}
    return dict(available=all(dependencies.values()) and all(weights.values()),dependencies=dependencies,weights=weights)


def _plane(result,vertices):
    import cv2
    import numpy as np
    kp=getattr(result,'keypoints',None)
    if kp is None or kp.xy is None or len(kp.xy)==0:return None
    xy=kp.xy.cpu().numpy();conf=kp.conf.cpu().numpy() if kp.conf is not None else None
    best=[]
    for n,row in enumerate(xy):
        points=[(i,(float(p[0]),float(p[1]))) for i,p in enumerate(row) if i<len(vertices) and (conf is None or conf[n,i]>=.5) and (p[0]>1 or p[1]>1)]
        if len(points)>len(best):best=points
    if len(best)<4:return None
    pitch=np.array([vertices[i] for i,_ in best],dtype=float);image=np.array([p for _,p in best],dtype=float)
    matrix,mask=cv2.findHomography(pitch,image,cv2.RANSAC,16.)
    if matrix is None or mask is None:return None
    residual=np.linalg.norm(cv2.perspectiveTransform(pitch.reshape(-1,1,2),matrix).reshape(-1,2)-image,axis=1)
    use=mask.ravel().astype(bool);ok,_=assess_homography(len(best),int(use.sum()),float(residual[use].mean()) if use.any() else None,max_error_px=40.,weak_error_px=18.)
    return invert_homography(tuple(tuple(float(x) for x in row) for row in matrix)) if ok else None


def extract_observations(video_path,timestamps,config,progress=lambda value:None,models=None):
    import cv2
    import numpy as np
    import torch
    if not isinstance(timestamps,list) or not 1<=len(timestamps)<=60 or any(type(t) is not int or t<0 or t>120000 for t in timestamps):
        raise ValueError('Select 1–60 valid timestamps')
    model_dir=Path(config['models_dir'])
    if models is None:
        if not available(model_dir)['available']:raise ValueError('Optional CV dependencies or local football weights unavailable; manual annotation remains supported')
        from ultralytics import YOLO
        models={k:YOLO(str(model_dir/v[0])) for k,v in HF_MODELS.items()}
    torch.set_num_threads(2);cv2.setNumThreads(1)
    cap=cv2.VideoCapture(str(video_path))
    if not cap.isOpened():raise ValueError('Video decoder failed')
    fps=float(cap.get(cv2.CAP_PROP_FPS));width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not 1<=fps<=240 or frames/fps>120.1 or width>3840 or height>2160:cap.release();raise ValueError('Media bounds exceeded')
    targets=sorted(set(timestamps)); output=[];next_target=0;frame_index=0;segment=0;identities={};previous={};last_t=None;tiny_prev=None
    teams=TeamBook();possessor=PossessorTracker();vertices=pitch_vertices_m();started=time.monotonic();detection_total=0;cuts=0
    try:
        while next_target<len(targets):
            ok,image=cap.read()
            if not ok:break
            timestamp=round(frame_index/fps*1000)
            if time.monotonic()-started>config.get('timeout_s',240):raise TimeoutError('CV job time limit exceeded')
            tiny=cv2.resize(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),(64,36)).astype(float)
            cut=tiny_prev is not None and scene_cut(float(np.abs(tiny-tiny_prev).mean()))
            tiny_prev=tiny
            if cut:
                cuts+=1;segment+=1;previous={};teams=TeamBook();possessor=PossessorTracker()
                for tracker in getattr(getattr(models['player'],'predictor',None),'trackers',[]):tracker.reset()
            detected=models['player'].track(image,persist=True,tracker='bytetrack.yaml',conf=.25,imgsz=640,device=config.get('device','cpu'),verbose=False)[0]
            ball_result=models['ball'].predict(image,conf=.2,imgsz=960,device=config.get('device','cpu'),verbose=False)[0]
            matrix=_plane(models['pitch'].predict(image,conf=.25,imgsz=640,device=config.get('device','cpu'),verbose=False)[0],vertices)
            rows=[];samples=[];box=detected.boxes
            if box is not None and box.id is not None:
                for xy,cls,confidence,tid in zip(box.xyxy.cpu().tolist(),box.cls.cpu().tolist(),box.conf.cpu().tolist(),box.id.cpu().tolist()):
                    role=str(detected.names[int(cls)]).lower()
                    if role not in ('player','goalkeeper'):continue
                    tid=int(tid);key=(segment,tid)
                    if key not in identities:identities[key]='T'+str(len(identities)+1).zfill(2)
                    x1,y1,x2,y2=xy;image_point=[(x1+x2)/2/width,y2/height];pitch=apply_homography(matrix,(x1+x2)/2,y2) if matrix else None
                    if pitch and not (0<=pitch[0]<=105 and 0<=pitch[1]<=68):pitch=None
                    crop=image[max(0,int(y1+.15*(y2-y1))):max(0,int(y1+.55*(y2-y1))),max(0,int(x1)):max(0,int(x2))]
                    rgb=summarize_jersey([tuple(map(float,p[::-1])) for p in crop.reshape(-1,3)[::max(1,crop.size//600)]]) if crop.size else None
                    samples.append((tid,role,rgb,pitch[0] if pitch else None))
                    vel=None
                    if pitch and key in previous and last_t is not None and timestamp>last_t:
                        vel=[(pitch[i]-previous[key][i])/((timestamp-last_t)/1000) for i in (0,1)]
                        if math.hypot(*vel)>12:vel=None
                    if pitch:previous[key]=pitch
                    rows.append(dict(player_id=identities[key],track_id=tid,team_id=None,image=image_point,pitch=list(pitch) if pitch else None,position='GK' if role=='goalkeeper' else None,
                        name=None,jersey_number=None,velocity=vel,confidence=float(confidence),human_verified=False,identity_status='temporary',observation_status='visible',
                        detection_confidence=float(confidence),tracking_confidence=None,team_confidence=None,coordinate_calibration_status='automatic_unverified' if pitch else 'unavailable',segment_id=segment))
            labels=teams.update(samples)
            for p in rows:
                label=labels.get(p['track_id'],'unknown').lower();p['team_id']=label.upper() if label in ('home','away') else None
            ball=None;ball_conf=None
            if ball_result.boxes is not None and len(ball_result.boxes)>0:
                boxes=ball_result.boxes;idx=int(boxes.conf.argmax());xy=boxes.xyxy[idx].cpu().tolist();ball=[(xy[0]+xy[2])/2/width,(xy[1]+xy[3])/2/height];ball_conf=float(boxes.conf[idx])
            fixes=[PlayerFix(p['track_id'],(p['image'][0]*width,p['image'][1]*height),(p['team_id'] or 'unknown').lower(),role='goalkeeper' if p['position']=='GK' else 'player') for p in rows]
            owner=possessor.update(fixes,(ball[0]*width,ball[1]*height) if ball else None,ball_visible=ball is not None)
            detection_total+=len(rows)
            # Take the latest causal frame at each requested timestamp, never future tracking.
            next_timestamp=round((frame_index+1)/fps*1000)
            while next_target<len(targets) and timestamp<=targets[next_target]<next_timestamp:
                output.append(dict(timestamp_ms=timestamp,frame_index=frame_index,requested_timestamp_ms=targets[next_target],players=rows,ball_image=ball,ball_confidence=ball_conf,
                    suggested_actor_id=next((p['player_id'] for p in rows if p['track_id']==owner.track_id),None),
                    homography_image_to_pitch=matrix,coordinate_calibration_status='automatic_unverified' if matrix else 'unavailable',human_verification_status='required',segment_id=segment))
                next_target+=1;progress(round(next_target/len(targets),3))
            last_t=timestamp;frame_index+=1
    finally:cap.release()
    return dict(schema_version=VERSION,frames=output,models={k:HF_MODELS[k][0] for k in HF_MODELS},frames_processed=frame_index,observations=detection_total,scene_cuts=cuts,
        unavailable_requested_timestamps=targets[next_target:],wall_seconds=round(time.monotonic()-started,3),fps=fps,width=width,height=height,limitations=['Automatic preannotations only. ByteTrack IDs are not jersey numbers.',
            'RGB teams are provisional; calibration, direction, possession and all used players require human verification.',
            'Fresh homography per frame; a failed fit or cut does not reuse stale pitch coordinates. No Softmax classification.'])
