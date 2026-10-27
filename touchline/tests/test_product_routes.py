"""Public Demo retirement and shared localhost/WSGI compatibility."""
import io
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

import server
import wsgi

ROOT=Path(__file__).resolve().parents[1]


class ProductRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def request(self,path,body=None,method=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                                   headers={'Content-Type':'application/json'},method=method)
        try:
            with urllib.request.urlopen(req) as response:return response.status,response.read()
        except urllib.error.HTTPError as error:
            with error:return error.code,error.read()

    def test_removed_public_bundle_and_builder_are_not_left_as_a_second_scorer(self):
        for name in ('index.html','inference.js','app.js','data.json','value-model.json','rates.json'):
            self.assertFalse((ROOT/'public-demo'/name).exists())
        self.assertFalse((ROOT/'build_public_demo.py').exists())
        self.assertTrue((ROOT/'decision/value-model.json').exists())
        self.assertTrue((ROOT/'coach.css').exists())

    def test_all_retired_urls_return_gone_for_get_and_head_including_normalized_paths(self):
        for method in ('GET','HEAD'):
            for path in ('/public-demo','/public-demo/','/public-demo/index.html','/public-demo/inference.js',
                         '/public-demo/value-model.json','/%70ublic-demo/index.html','/unused/../public-demo/app.js'):
                status,body=self.request(path,method=method);self.assertEqual(status,410,(method,path,body))
                if method=='GET':self.assertIn(b'Public Demo retired',body)

    def test_azure_wsgi_uses_the_same_retirement_route_without_changing_its_entry_point(self):
        status=[]
        environ={'REQUEST_METHOD':'GET','PATH_INFO':'/public-demo/index.html','QUERY_STRING':'',
                 'HTTP_HOST':'127.0.0.1:5173','wsgi.input':io.BytesIO(b'')}
        body=b''.join(wsgi.application(environ,lambda value,headers:status.append(value)))
        self.assertTrue(status[0].startswith('410'));self.assertIn(b'Public Demo retired',body)

    def test_shared_match_model_and_decision_api_are_preserved(self):
        self.assertEqual(self.request('/index.html')[0],200)
        self.assertEqual(self.request('/decision/value-model.json')[0],200)
        status,data=self.request('/api/decision-analysis/catalog')
        self.assertEqual(status,200);self.assertEqual(len(json.loads(data)['matches']),40)

    def test_video_revision_and_partial_fields_cannot_enter_the_synthetic_counterfactual_service(self):
        _,data=self.request('/api/decision-analysis/context?match_id=PL26-W01-MCI-CHE&decision_id=d000001')
        context=json.loads(data);_,data=self.request('/api/decision-analysis/analyze',context['request']);doc=json.loads(data)
        bound=dict(request=context['request'],candidate_set_id=doc['candidate_set_id'],action_id='carry:forward')
        for key in ('video_id','revision_id','assumption_set_id','visibility_scope_id'):
            self.assertEqual(self.request('/api/decision-analysis/counterfactual',{**bound,key:'not-supported'})[0],400)
        request={**context['request'],'mode':'partial_observation'}
        self.assertEqual(self.request('/api/decision-analysis/counterfactual',{**bound,'request':request})[0],400)


if __name__=='__main__':unittest.main()
