"""Opt-in real-weight acceptance harness. No external video downloading or upload.

python -m video_review.validate_cv --video /path/owned.mp4 --source '...' --rights-confirmed --models /path --output /tmp/result.json
Exit 2 means the real run did not yield any mapped player; it is not a mock pass.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--video',required=True);p.add_argument('--source',required=True);p.add_argument('--rights-confirmed',action='store_true');p.add_argument('--models',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    if not args.rights_confirmed:p.error('Confirm video authorization explicitly')
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
    from demo.observations import extract_observations
    from demo.weights import HF_MODELS
    path=Path(args.video);report=dict(source=args.source,rights='operator_confirmed',video_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),real_weights=True,
        models={k:dict(file=v[0],sha256=hashlib.sha256((Path(args.models)/v[0]).read_bytes()).hexdigest()) for k,v in HF_MODELS.items() if (Path(args.models)/v[0]).is_file()},
        versions={x:importlib.metadata.version(x) for x in ('ultralytics','torch','opencv-python','lap')})
    try:
        result=extract_observations(path,[0,500,1000],dict(models_dir=args.models,timeout_s=240));report['result']=result
        mapped=sum(sum(p['pitch'] is not None for p in f['players']) for f in result['frames'])
        report.update(mapped_player_observations=mapped,automatically_verified_frames=0,scorable_frames=0,
            status='detections_require_human_verification' if mapped else 'no_mapped_players',
            note='Real CV output requires human confirmation before Q2. Zero observations is a negative result, not successful football understanding.')
    except Exception as e:report.update(status='failed',error=type(e).__name__+': '+str(e))
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return 0 if report.get('mapped_player_observations',0)>0 else 2


if __name__=='__main__':raise SystemExit(main())
