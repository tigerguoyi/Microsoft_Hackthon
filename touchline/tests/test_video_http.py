"""Actual local HTTP/WSGI security, media decoding and annotation workflow."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from server import Handler
from video_review import storage
from test_video_analysis import draft_for


class VideoHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.store=patch.object(storage,'ROOT',cls.root/'private');cls.store.start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.store.stop();cls.tmp.cleanup()

    def request(self,path,body=None,headers=None):
        h={'Content-Type':'application/json'} if body is not None else {};h.update(headers or {})
        if body is not None and not isinstance(body,bytes):body=json.dumps(body).encode()
        try:
            response=urllib.request.urlopen(urllib.request.Request(self.url+path,body,h),timeout=30)
        except urllib.error.HTTPError as e:response=e
        content=response.read()
        return response.status,response.headers,json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content

    def session(self):
        status,h,c=self.request('/api/video-review/config');self.assertEqual(status,200);self.assertTrue(c['enabled'])
        return {'Cookie':h['Set-Cookie'].split(';')[0],'X-Video-CSRF':c['csrf']}

    def test_public_defaults_and_cross_origin_access_fail_closed(self):
        with patch.dict(os.environ,{'WEBSITE_INSTANCE_ID':'production'}):
            status,_,value=self.request('/api/video-review/config');self.assertEqual(status,200);self.assertFalse(value['enabled'])
            self.assertEqual(self.request('/api/video-review/assets')[0],403)
        self.assertEqual(self.request('/api/video-review/config',headers={'Origin':'https://evil.example'})[2]['enabled'],False)
        self.assertEqual(self.request('/api/video-review/assets')[0],403)

    def test_no_private_operation_without_csrf_or_rights(self):
        h=self.session()
        self.assertEqual(self.request('/api/video-review/confirm',{'annotation':{}},headers={'Cookie':h['Cookie']})[0],403)
        self.assertEqual(self.request('/api/video-review/upload',b'x'*100,headers={**h,'Content-Type':'video/mp4'})[0],400)
        self.assertEqual(self.request('/api/video-review/upload',b'x'*100,headers={**h,'Content-Type':'video/mp4','X-Video-Rights':'confirmed'})[0],400)

    @unittest.skipUnless(importlib.util.find_spec('cv2'),'Optional decoder integration requires opencv')
    def test_real_decoded_media_manual_partial_sensitivity_and_counterfactual(self):
        import cv2
        import numpy as np
        path=self.root/'owned-test.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10.,(320,180))
        for i in range(20):writer.write(np.full((180,320,3),(40,110,45),dtype=np.uint8))
        writer.release();h=self.session()
        status,_,a=self.request('/api/video-review/upload',path.read_bytes(),headers={**h,'Content-Type':'video/mp4','X-Video-Rights':'confirmed'})
        self.assertEqual(status,201,a);self.assertTrue(a['decoder_verified']);vid=a['video_id']
        self.assertFalse((Path(__file__).resolve().parents[1]/'data'/vid).exists())
        self.assertEqual(self.request('/api/video-review/media/'+vid,headers=h)[0],200)
        code,headers,block=self.request('/api/video-review/media/'+vid,headers={**h,'Range':'bytes=0-19'});self.assertEqual(code,206);self.assertEqual(len(block),20)
        other=self.session();self.assertEqual(self.request('/api/video-review/media/'+vid,headers=other)[0],404)
        status,_,record=self.request('/api/video-review/confirm',{'annotation':draft_for(vid)},h);self.assertEqual(status,200,record)
        selection=dict(video_id=vid,revision_id=record['revision_id'],frame_index=0,visibility_scope='verified',selected_player_ids=None,assumption_set_id='moderate_pressure_v1',include_shot=False)
        status,_,r=self.request('/api/video-review/analyze',selection,h);self.assertEqual(status,200,r);self.assertEqual(len(r['ranking']),7)
        status,_,s=self.request('/api/video-review/sensitivity',selection,h);self.assertEqual(status,200);self.assertFalse(s['top_choice_stability']['stable'])
        bound={k:r[k] for k in ('snapshot_id','candidate_set_id','analysis_id')}
        status,_,cf=self.request('/api/video-review/counterfactual',dict(selection=selection,**bound,action_id='carry:forward'),h);self.assertEqual(status,200,cf);self.assertEqual(cf['candidate_set_id'],r['candidate_set_id'])
        with patch('server.read_config',return_value={}):
            status,_,answer=self.request('/api/video-review/agents',dict(selection=selection,**bound,question='Compare',mode='fan',language='en'),h)
            self.assertEqual(status,200);self.assertEqual(answer['status'],'model_unavailable')
        with patch('video_review.jobs.capabilities',return_value={'available':False}):
            self.assertEqual(self.request('/api/video-review/detect',dict(video_id=vid,timestamps=[0]),h)[0],400)
        self.assertEqual(self.request('/api/video-review/analyze',selection,other)[0],404)
        self.assertEqual(self.request('/api/video-review/delete',dict(video_id=vid),h)[0],200)
        self.assertEqual(self.request('/api/video-review/media/'+vid,headers=h)[0],404)

    def test_wsgi_rejects_oversized_body_without_reading(self):
        from wsgi import application
        class NeverRead:
            def read(self,*args):raise AssertionError('Unbounded request read')
        environ={'REQUEST_METHOD':'POST','PATH_INFO':'/api/video-review/upload','CONTENT_LENGTH':str(65*1024*1024),'HTTP_HOST':'127.0.0.1:5173','wsgi.input':NeverRead()}
        output=[];body=b''.join(application(environ,lambda status,headers:output.append(status)))
        self.assertTrue(output[0].startswith('413'));self.assertIn(b'too large',body)


if __name__=='__main__':unittest.main()
