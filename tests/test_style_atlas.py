"""Optional bundled atlas: real HTTP delivery, bounded paths and offline UI logic."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import storyboard


class StyleAtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.install=root/'skill';self.install.mkdir()
        for name in ('scripts','assets'):
            shutil.copytree(storyboard.ROOT/name,self.install/name,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(storyboard.ROOT/'SKILL.md',self.install/'SKILL.md')
        self.atlas=self.install/'assets/visual-style-atlas'
        self.project=root/'project';storyboard.Store(self.project).create('Atlas test')
        self.before=(self.project/'storyboard.json').read_bytes()
        outside=root/'outside';outside.mkdir();(outside/'private.jpg').write_bytes(b'private file must not be served')
        (self.atlas/'images/escape.jpg').symlink_to(outside/'private.jpg')
        (self.atlas/'images/escape-directory').symlink_to(outside,target_is_directory=True)
        self.process=subprocess.Popen([sys.executable,str(self.install/'scripts/storyboard.py'),'serve',
                                       '--directory',str(self.project)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(self.stop)
        self.url=self.process.stdout.readline().strip()
        self.assertTrue(self.url.startswith('http://127.0.0.1:'),self.url)

    def stop(self):
        if self.process.poll() is None:self.process.terminate()
        self.process.wait(timeout=5);self.process.stdout.close();self.process.stderr.close()

    def get(self,path):
        with urllib.request.urlopen(self.url+path,timeout=5) as response:
            return response.read(),response.headers

    def assert_missing(self,path):
        with self.assertRaises(urllib.error.HTTPError) as result:self.get(path)
        self.assertEqual(result.exception.code,404,path);result.exception.close()

    def test_optional_menu_and_page_specific_csp(self):
        home,headers=self.get('/')
        self.assertIn(b'id="open-style"',home)
        self.assertIn(b'id="style-library"',home)
        self.assertNotIn(b'<iframe',home)
        self.assertNotIn("'unsafe-inline'",headers['Content-Security-Policy'])
        page,headers=self.get('/style-atlas/index.html?recommend=clay,natural')
        self.assertEqual(page,(self.atlas/'index.html').read_bytes())
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertIn("style-src 'self'",headers['Content-Security-Policy'])
        self.assertIn("connect-src 'none'",headers['Content-Security-Policy'])
        self.assertNotIn(b'<script>',page)
        self.assertNotIn(b'<style>',page)
        self.assertIn(b'data-cinematic-atlas-root',page)
        self.assertEqual(headers.get_content_type(),'text/html')
        for path in ('/api/document','/app.js','/style-atlas/atlas-data.js','/style-atlas/app.js','/style-atlas/full-page.css'):
            _,headers=self.get(path);self.assertNotIn("'unsafe-inline'",headers['Content-Security-Policy'])
        self.assertEqual((self.project/'storyboard.json').read_bytes(),self.before)
        self.assertFalse((self.project/'visual-style-atlas').exists())

    def test_actual_catalog_images_and_local_links_are_served(self):
        payload,headers=self.get('/style-atlas/atlas.json');catalog=json.loads(payload)
        self.assertEqual(headers.get_content_type(),'application/json')
        self.assertTrue(catalog['assets'])
        for asset in catalog['assets']:
            with self.subTest(image=asset['path']):
                image,headers=self.get('/style-atlas/'+urllib.parse.quote(asset['path']))
                self.assertEqual(hashlib.sha256(image).hexdigest(),asset['sha256'])
                self.assertTrue(headers.get_content_type().startswith('image/'))
        page=(self.atlas/'index.html').read_text()
        links=re.findall(r'(?:href|src)="([^"]+)"',page)
        local=[link for link in links if not urllib.parse.urlparse(link).scheme and not any(c in link for c in ('#','$','{'))]
        self.assertTrue(local)
        for link in local:
            with self.subTest(link=link):self.get('/style-atlas/'+urllib.parse.quote(link))

    def test_path_traversal_code_and_link_escapes_are_rejected(self):
        for path in (
            '/style-atlas/','/style-atlas/images/','/style-atlas/README.md',
            '/style-atlas/tools/rebuild_views.py','/style-atlas/../scripts/storyboard.py',
            '/style-atlas/%2e%2e/scripts/storyboard.py','/style-atlas/images/%2e%2e/atlas.json',
            '/style-atlas/images/%2e%2e/%2e%2e/%2e%2e/scripts/storyboard.py',
            '/style-atlas/%2fetc/passwd','/style-atlas/images%5c..%5cstoryboard.py',
            '/style-atlas/images/escape.jpg','/style-atlas/images/escape-directory/private.jpg',
            '/style-atlas/images/missing.jpg','/style-atlas/images/%00.jpg',
        ):
            with self.subTest(path=path):self.assert_missing(path)
        # Even an otherwise allowed root document cannot expose a symlink target.
        (self.atlas/'index.html').unlink();(self.atlas/'index.html').symlink_to(self.install/'scripts/storyboard.py')
        with patch.object(storyboard,'ROOT',self.install):self.assertIsNone(storyboard.atlas_file('index.html'))

    def test_build_tracks_page_script_data_without_hashing_images(self):
        with patch.object(storyboard,'ROOT',self.install):
            baseline=storyboard.runtime_signature()
            for name in ('index.html','app.js','full-page.css','atlas-data.js','atlas.json','glossary.md'):
                path=self.atlas/name;original=path.read_bytes();path.write_bytes(original+b'\n')
                self.assertNotEqual(storyboard.runtime_signature(),baseline,name)
                path.write_bytes(original)
            image=next((self.atlas/'images').glob('oa-*.jpg'));image.write_bytes(image.read_bytes()+b'changed')
            self.assertEqual(storyboard.runtime_signature(),baseline)
            # Safe root documents are frozen with the running frontend release.
            script=self.atlas/'atlas-data.js';original=script.read_bytes();script.write_bytes(original+b'\nchanged')
            served,_=self.get('/style-atlas/atlas-data.js');self.assertEqual(served,original)
            health=json.loads(self.get('/api/health')[0]);self.assertFalse(health['current'])

    def run_atlas(self,search='',actions=False,standalone=False):
        data_script=self.get('/style-atlas/atlas-data.js')[0].decode()
        script=self.get('/style-atlas/app.js')[0].decode()
        program=r'''
const vm=require('node:vm'),fs=require('node:fs'),input=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
const elements=new Map(),listeners=new Map(),scrolls=[],saves=[];let focused=0,styleHref='';
function element(id){
 if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',style:{},hidden:false,open:false,isConnected:true,
 classList:{toggle(){}},setAttribute(){},addEventListener(type,fn){listeners.set(id+':'+type,fn)},removeEventListener(type){listeners.delete(id+':'+type)},
 showModal(){this.open=true},close(){this.open=false;listeners.get(id+':close')?.({target:this})},focus(){focused++},select(){},remove(){}});
 return elements.get(id);
}
const doc={baseURI:'http://example.test/workbench/',currentScript:{src:'http://example.test/style-atlas/app.js'},
 documentElement:{style:{overflow:'scroll'}},body:{style:{overflow:'visible'}},activeElement:element('focus'),
 createElement:()=>element('link'),querySelector:()=>input.standalone?root:null};
const view={location:{search:input.search},innerWidth:1200,scrollX:8,scrollY:230,scrollTo(x,y){scrolls.push([x,y])},navigator:{clipboard:{writeText:async()=>{}}}};
doc.defaultView=view;
const root={ownerDocument:doc,activeElement:element('focus'),
 querySelector:selector=>element(selector.slice(1)),
 querySelectorAll:selector=>selector==='dialog'?[element('detail'),element('comparison')]:[],
 prepend(node){styleHref=node.href}};
const context={window:view,document:doc,URL,URLSearchParams,Blob,setTimeout,fetch(){throw new Error('Network must not be used');}};
vm.createContext(context);vm.runInContext(input.data,context);vm.runInContext(input.script,context);
let api;if(!input.standalone)api=view.CinematicAtlas.mount(root,view.STYLE_ATLAS,{assetBase:'/style-atlas/',onSave:async choice=>{saves.push(choice);return true;}});
const result={html:element('cards').innerHTML,note:element('viewNote').textContent,brief:element('brief').value,styleHref};
if(input.actions){
 const click=(id,dataset)=>listeners.get(id+':click')({target:{closest:()=>({dataset})}});
 click('cards',{select:'clay'});element('projectNotes').value='保留蓝色品牌与正常连续动作';element('projectNotes').oninput();
 click('tones',{tone:'温暖治愈'});click('cards',{select:'flat'});
 result.choice=api.getChoice();await element('saveProject').onclick();result.saved=saves[0];
 element('all').onclick();result.allCount=element('count').textContent;
 element('search').value='粘土';element('search').oninput();result.searchHTML=element('cards').innerHTML;
 click('cards',{detail:'clay'});result.locked=[doc.documentElement.style.overflow,doc.body.style.overflow];result.detailHTML=element('detailBody').innerHTML;
 element('closeDetail').onclick();result.unlocked=[doc.documentElement.style.overflow,doc.body.style.overflow];result.scrolls=scrolls;result.focused=focused;
 click('cards',{compare:'clay'});click('cards',{compare:'flat'});element('compare').onclick();result.compareHTML=element('compareBody').innerHTML;element('closeCompare').onclick();
 api.restoreChoice({brief:'旧自定义风格说明：不要缩放人物，保留真实比例'});result.legacy=api.getChoice();
 api.restoreChoice(result.choice);result.restored=api.getChoice();
 api.destroy();result.listenersRemaining=listeners.size;
}
process.stdout.write(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exit(1)});
'''
        result=subprocess.run(['node','-e',program],input=json.dumps({'search':search,'data':data_script,'script':script,'actions':actions,'standalone':standalone}),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    @unittest.skipUnless(shutil.which('node'),'Requires Node for the shipped atlas script')
    def test_recommend_parameter_renders_requested_cards_without_network(self):
        for standalone in (False,True):
            for search,expected in [('?recommend=clay,natural',['clay','natural']),('?recommend=unknown,natural',['natural'])]:
                rendered=self.run_atlas(search,standalone=standalone)
                self.assertEqual(re.findall(r'data-detail="([^"]+)"',rendered['html']),expected)
                self.assertIn('传入的推荐清单',rendered['note']);self.assertEqual(rendered['brief'],'')
                self.assertTrue(all(src.startswith('http://example.test/style-atlas/images/') for src in re.findall(r'<img src="([^"]+)"',rendered['html'])))
                self.assertEqual(rendered['styleHref'],'http://example.test/style-atlas/full-page.css')

    @unittest.skipUnless(shutil.which('node'),'Requires Node for the shipped atlas script')
    def test_mounted_atlas_keeps_notes_save_and_modal_scroll_contract(self):
        result=self.run_atlas(actions=True)
        self.assertEqual(result['choice']['base_id'],'flat')
        self.assertEqual(result['choice']['tones'],['温暖治愈'])
        self.assertEqual(result['choice']['project_notes'],'保留蓝色品牌与正常连续动作')
        self.assertEqual(result['saved'],result['choice']);self.assertEqual(result['restored'],result['choice'])
        self.assertIn('28',result['allCount']);self.assertIn('data-detail="clay"',result['searchHTML'])
        self.assertEqual(result['locked'],['hidden','hidden']);self.assertEqual(result['unlocked'],['scroll','visible'])
        self.assertIn([8,230],result['scrolls']);self.assertGreaterEqual(result['focused'],1)
        self.assertIn('style-atlas/images/',result['detailHTML']);self.assertIn('style-atlas/images/',result['compareHTML'])
        self.assertIn('旧自定义风格说明',result['legacy']['brief']);self.assertIn('保留真实比例',result['legacy']['project_notes'])
        self.assertEqual(result['listenersRemaining'],0)

    def test_full_page_template_has_no_embedded_scroller(self):
        page=self.get('/style-atlas/index.html')[0].decode()
        css=self.get('/style-atlas/full-page.css')[0].decode()
        script=self.get('/style-atlas/app.js')[0].decode()
        self.assertNotIn('<iframe',page);self.assertNotIn('postMessage',script)
        self.assertNotIn('.embedded',css)
        self.assertIn(':host',css)
        self.assertIn('dialog{overflow:auto;',css)
        self.assertIn('.modalbody{overflow:visible}',css)
        self.assertNotRegex(css,r'\.(?:wrap|layout)\{[^}]*overflow\s*:')


if __name__=='__main__':unittest.main()
