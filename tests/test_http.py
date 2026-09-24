import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
import test_store

class HttpTests(unittest.TestCase):
    def setUp(self):
        test_store.StoreTests.setUp(self)
        self.proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/storyboard.py'),'serve','--directory',self.tmp.name],stdout=subprocess.PIPE,text=True)
        self.addCleanup(self.stop)
        self.url=self.proc.stdout.readline().strip()
        self.token=self.get('/api/session')['token']
    def add_derived(self):
        return test_store.StoreTests.add_derived(self)
    def stop(self):
        self.proc.terminate();self.proc.wait(timeout=5);self.proc.stdout.close()
    def get(self,path):
        with urllib.request.urlopen(self.url+path) as r:return json.load(r)
    def post(self,path,body,extra=None):
        headers={'Content-Type':'application/json','X-Storyboard-Token':self.token}
        if extra:headers.update(extra)
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers=headers)
        with urllib.request.urlopen(req) as r:return json.load(r)
    def test_registered_image_and_changed_file(self):
        import base64
        image=Path(self.tmp.name)/'sample.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
        record={'id':'picture','kind':'decision','title':'图稿','body':'候选','section_ids':[self.doc['sections'][0]['id']],'files':[{'path':'sample.png','role':'storyboard_candidate'}],'data':{}}
        self.post('/api/production/records',{'record':record,'expected_revision':0})
        with urllib.request.urlopen(self.url+'/api/image?record=picture&file=0') as response:
            self.assertEqual(response.headers['Content-Type'],'image/png')
            self.assertEqual(response.read(),image.read_bytes())
        for path in ['/api/image?record=missing&file=0','/api/image?record=picture&file=-1','/api/image?path=/etc/passwd']:
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.get(path)
            self.assertEqual(ctx.exception.code,404);ctx.exception.close()
        image.write_bytes(b'changed')
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.get('/api/image?record=picture&file=0')
        self.assertEqual(ctx.exception.code,409);ctx.exception.close()

    def test_actual_input_image_is_scoped_and_hash_checked(self):
        import base64,hashlib,tempfile
        payload=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        image=Path(self.tmp.name)/'source.png';image.write_bytes(payload)
        record={'id':'board','kind':'decision','title':'测试分镜图','body':'用图追踪','section_ids':[self.doc['sections'][0]['id']],
                'data':{'actual_inputs':[{'path':'source.png','purpose':'空间参考','sha256':hashlib.sha256(payload).hexdigest()}]}}
        self.post('/api/production/records',{'record':record,'expected_revision':0})
        with urllib.request.urlopen(self.url+'/api/image?record=board&input=0') as response:self.assertEqual(response.read(),payload)
        image.write_bytes(b'changed')
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.get('/api/image?record=board&input=0')
        self.assertEqual(ctx.exception.code,409);ctx.exception.close()
        with tempfile.TemporaryDirectory() as outside:
            secret=Path(outside)/'secret.png';secret.write_bytes(payload)
            record['data']['actual_inputs']=[{'path':str(secret),'purpose':'外部图片'}]
            self.post('/api/production/records',{'record':record,'expected_revision':1})
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.get('/api/image?record=board&input=0')
            self.assertEqual(ctx.exception.code,403);ctx.exception.close()

    def test_http_roundtrip(self):
        d=self.get('/api/document');d['title']='中文🚦 <script>安全文本</script>'
        out=self.post('/api/document',{'document':d,'expected_revision':0})
        self.assertEqual(out['revision'],1);self.assertEqual(self.get('/api/document')['title'],d['title'])
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.post('/api/document',{'document':d,'expected_revision':0})
        self.assertEqual(ctx.exception.code,409)
        ctx.exception.close()
    def test_http_reject_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.post('/api/document',{'document':self.doc,'expected_revision':0},{'Origin':'https://example.com'})
        self.assertEqual(ctx.exception.code,403)
        ctx.exception.close()
    def test_http_reject_token(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.post('/api/document',{'document':self.doc,'expected_revision':0},{'X-Storyboard-Token':'bad'})
        self.assertEqual(ctx.exception.code,403)
        ctx.exception.close()
    def test_http_reject_traversal(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.get('/../../storyboard.json')
        self.assertEqual(ctx.exception.code,404)
        ctx.exception.close()
    def test_http_ignore(self):
        d=self.add_derived();sid=d['suggestions'][0]['id']
        out=self.post('/api/suggestions/'+sid+'/ignore',{'expected_revision':d['revision']})
        self.assertEqual(out['suggestions'][0]['status'],'ignored')
    def test_confirm_then_record_http_and_protect_snapshot(self):
        sid=self.doc['sections'][0]['id']
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.get('/api/markdown')
        self.assertEqual(ctx.exception.code,409);ctx.exception.close()
        d=self.post('/api/sections/confirm',{'section_id':sid,'expected_revision':0,'evidence':'隔离HTTP测试确认'})
        self.assertEqual(d['_section_status'][sid],'confirmed')
        r={'id':'D','kind':'decision','title':'测试决定','body':'保留决定','section_ids':[sid],'data':{}}
        d=self.post('/api/production/records',{'record':r,'expected_revision':d['revision']})
        d['production']['confirmations']={}
        d=self.post('/api/document',{'document':d,'expected_revision':d['revision']})
        self.assertIn(sid,d['production']['confirmations'])
        with urllib.request.urlopen(self.url+'/api/markdown') as response:text=response.read().decode()
        self.assertIn('保留决定',text)
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.post('/api/production/records',{'record':r,'expected_revision':0})
        self.assertEqual(ctx.exception.code,409);ctx.exception.close()
    def test_restart_retains_saved_document(self):
        d=self.get('/api/document');d['title']='重启后保留'
        self.post('/api/document',{'document':d,'expected_revision':0})
        port=self.url.rsplit(':',1)[1];oldtoken=self.token;self.stop()
        self.proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/storyboard.py'),'serve','--directory',self.tmp.name,'--port',port],stdout=subprocess.PIPE,text=True)
        self.assertEqual(self.proc.stdout.readline().strip(),self.url)
        self.assertEqual(self.get('/api/document')['title'],'重启后保留')
        self.assertNotEqual(self.get('/api/session')['token'],oldtoken)

if __name__=='__main__':unittest.main()
