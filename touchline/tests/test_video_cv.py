"""Optional CV integration units: injected detector, real frame/geometry adapter.

This is explicitly not the real-weights acceptance run in docs/reports/video-real-validation.json.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

SRC=Path(__file__).resolve().parents[2]/'src';sys.path.insert(0,str(SRC))


@unittest.skipUnless(all(importlib.util.find_spec(x) for x in ('torch','cv2')),'Optional CV dependencies absent')
class CVAdapterTests(unittest.TestCase):
    def test_mock_detection_tracks_are_preannotations_and_bad_calibration_never_becomes_metres(self):
        import cv2
        import numpy as np
        import torch
        from demo.observations import extract_observations
        class Model:
            names={0:'player'}
            def __init__(self,kind):self.kind=kind
            def track(self,*args,**kw):
                self.asserted_tracker=kw['tracker'];return [types.SimpleNamespace(names=self.names,boxes=types.SimpleNamespace(xyxy=torch.tensor([[60.,40.,90.,150.]]),cls=torch.tensor([0.]),conf=torch.tensor([.9]),id=torch.tensor([17.])))]
            def predict(self,*args,**kw):return [types.SimpleNamespace(boxes=None,keypoints=None)]
        models={x:Model(x) for x in ('player','ball','pitch')}
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'owned-generated.mp4';w=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10.,(320,180))
            for i in range(3):w.write(np.full((180,320,3),(50,140,50),dtype=np.uint8))
            w.release();result=extract_observations(path,[0,100],{'models_dir':t},models=models)
        self.assertEqual(models['player'].asserted_tracker,'bytetrack.yaml');self.assertEqual(len(result['frames']),2)
        p=result['frames'][0]['players'][0];self.assertEqual(p['track_id'],17);self.assertEqual(p['player_id'],'T01');self.assertIsNone(p['jersey_number']);self.assertFalse(p['human_verified']);self.assertIsNone(p['pitch'])
        self.assertEqual(result['frames'][1]['players'][0]['player_id'],'T01');self.assertEqual(result['frames'][0]['coordinate_calibration_status'],'unavailable')

    def test_homography_projector_preserves_real_units_and_rejects_collinear_points(self):
        from video_review.geometry import calibrate,project
        result=calibrate([dict(image=[x,y],pitch=[x*105,y*68]) for x,y in [(0,0),(1,0),(1,1),(0,1)]])
        self.assertEqual(project(result['matrix'],[.5,.5]),[52.5,34.])
        with self.assertRaises(ValueError):calibrate([dict(image=[i/4,0],pitch=[i*20,0]) for i in range(4)])


if __name__=='__main__':unittest.main()
