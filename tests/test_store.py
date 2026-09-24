import copy
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from storyboard import Store,new_document,new_shot,Conflict,uid

def fixture():
    d=new_document('测试：光的去处')
    a=new_shot();a.update(number='SH01',content='停电。\n她抬头：<script>alert(1)</script>',duration=3)
    b=new_shot();b.update(number='SH02',content='灯打开，照亮手上的陶碗。',duration=None)
    d['sections']=[dict(id=uid(),title='夜间工作',notes='',groups=[dict(id=uid(),title='从暗到明',notes='',shots=[a,b])])]
    return d

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.doc=self.store.create('测试',fixture())
    def test_reject_skill_data_directory_and_symlink(self):
        from storyboard import ROOT
        for path in [ROOT,ROOT/'assets'/'project-data']:
            with self.assertRaisesRegex(ValueError,'Skill安装目录'):Store(path)
        link=Path(self.tmp.name)/'skill-link'
        link.symlink_to(ROOT,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Skill安装目录'):Store(link/'project-data')

    def add_derived(self):
        d=copy.deepcopy(self.doc);shots=d['sections'][0]['groups'][0]['shots']
        for shot in shots:
            d['prompts'].append(dict(id=uid(),title=shot['number'],shot_ids=[shot['id']],text='画一幅静态关键帧',references='人物母图',constraints='同一服装',base_revision=d['revision']))
        d['suggestions']=[dict(id=uid(),target_id=shots[0]['id'],problem='动作不够明确',impact='便于表演',changes={'content':'她停笔，抬头看向熄灭的灯。'},base_revision=d['revision'],status='pending')]
        return self.store.update(d,d['revision'])
    def test_unicode_and_exports(self):
        self.assertFalse(Path(self.tmp.name,'分镜阅览.md').exists())
        d=self.store.read();self.assertEqual(d,self.doc)
        self.store.confirm(d['sections'][0]['id'],d['revision'],'用户确认')
        self.assertIn('停电。<br>她抬头',Path(self.tmp.name,'分镜阅览.md').read_text())
    def test_source_text_precedes_brief_and_changes_confirmation(self):
        d=copy.deepcopy(self.doc);d['source_text']='原文第一句。\n## 修改建议\n原文第二句。';d['brief']='制作需求另行说明。'
        d=self.store.update(d,d['revision'])
        d=self.store.confirm(d['sections'][0]['id'],d['revision'],'确认这一版')
        text=Path(self.tmp.name,'分镜阅览.md').read_text()
        self.assertLess(text.index('原文第一句。'),text.index('制作需求另行说明。'))
        self.assertIn('原文第二句。',Path(self.tmp.name,'制作记录.md').read_text())
        d['source_text']='原文已修订。'
        d=self.store.update(d,d['revision'])
        self.assertEqual(d['_section_status'][d['sections'][0]['id']],'changed')
        self.assertIn('原文已修订。',Path(self.tmp.name,'分镜阅览.md').read_text())
    def test_legacy_document_without_source_text_stays_readable(self):
        d=copy.deepcopy(self.doc);d.pop('source_text')
        d=self.store.update(d,d['revision'])
        d=self.store.confirm(d['sections'][0]['id'],d['revision'],'确认旧格式')
        self.assertEqual(d['_section_status'][d['sections'][0]['id']],'confirmed')
        self.assertNotIn('## 对应原文',Path(self.tmp.name,'分镜阅览.md').read_text())
    def test_tables_preserve_fields_and_refresh(self):
        d=copy.deepcopy(self.doc)
        shot=d['sections'][0]['groups'][0]['shots'][0]
        for key in ('framing','camera','sound','start','end','transition','assets','reason','notes'):
            shot[key]=key+'：甲 | 乙\n<script> & 文本'
        d=self.store.update(d,0)
        self.store.confirm(d['sections'][0]['id'],d['revision'],'用户确认本版')
        result=Path(self.tmp.name,'分镜阅览.md').read_text()
        for key in ('framing','camera','sound','start','end','transition','assets','reason','notes'):
            self.assertIn(key+'：甲 &#124; 乙<br>&lt;script&gt; &amp; 文本',result)
        self.assertIn('待定',result)
        self.assertNotIn('<script>',result)
        self.assertEqual(result.count('| SH01 |'),1)
        self.assertLess(result.index('| SH01 |'),result.index('| SH02 |'))
        self.assertIn('修订 1',result)
    def test_read_does_not_churn_exports(self):
        self.store.confirm(self.doc['sections'][0]['id'],0,'用户确认')
        p=Path(self.tmp.name,'分镜阅览.md');before=p.stat().st_mtime_ns
        self.store.read();self.assertEqual(p.stat().st_mtime_ns,before)
    def test_revision_rejects_stale(self):
        d=copy.deepcopy(self.doc);d['title']='修改稿';self.store.update(d,0)
        with self.assertRaises(Conflict):self.store.update(self.doc,0)
        self.assertEqual(self.store.read()['title'],'修改稿')
    def test_concurrent_writers(self):
        result=[]
        def write():
            try:self.store.update(self.doc,0);result.append('ok')
            except Conflict:result.append('conflict')
        threads=[threading.Thread(target=write) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(result,['ok','conflict'])
    def test_precise_staleness(self):
        d=self.add_derived();d['sections'][0]['groups'][0]['shots'][0]['content']='人工修改'
        d=self.store.update(d,d['revision'])
        self.assertEqual([x['status'] for x in d['prompts']],['stale','current'])
        self.assertTrue(d['suggestions'][0]['stale'])
        with self.assertRaises(Conflict):self.store.decide(d['suggestions'][0]['id'],'accept',d['revision'])
    def test_suggestion_accept_and_ignore(self):
        d=self.add_derived();sid=d['suggestions'][0]['id']
        d=self.store.decide(sid,'accept',d['revision'])
        self.assertEqual(d['suggestions'][0]['status'],'accepted')
        self.assertEqual(d['sections'][0]['groups'][0]['shots'][0]['content'],'她停笔，抬头看向熄灭的灯。')
        with self.assertRaises(Conflict):self.store.decide(sid,'accept',d['revision'])
    def test_cannot_forge_accepted_status(self):
        d=self.add_derived();d['suggestions'][0]['status']='accepted'
        d=self.store.update(d,d['revision'])
        self.assertEqual(d['suggestions'][0]['status'],'pending')
    def test_rewrite_prompt_rebinds_current_content(self):
        d=self.add_derived();d['sections'][0]['groups'][0]['shots'][0]['content']='变更'
        d=self.store.update(d,d['revision']);p=d['prompts'][0]
        p['text']='更新后的静帧';p['base_revision']=d['revision']
        d=self.store.update(d,d['revision']);self.assertEqual(d['prompts'][0]['status'],'current')
    def test_deleted_reference_stales_existing(self):
        d=self.add_derived();d['sections'][0]['groups'][0]['shots'].pop(0)
        d=self.store.update(d,d['revision']);self.assertEqual(d['prompts'][0]['status'],'stale')
    def test_duplicate_id_rejected(self):
        d=copy.deepcopy(self.doc);g=d['sections'][0]['groups'][0];g['shots'].append(copy.deepcopy(g['shots'][0]))
        with self.assertRaises(ValueError):self.store.update(d,0)
    def test_nonfinite_duration_rejected(self):
        d=copy.deepcopy(self.doc);d['sections'][0]['groups'][0]['shots'][0]['duration']=float('nan')
        with self.assertRaises(ValueError):self.store.update(d,0)
    def test_output_symlink_rejected(self):
        p=Path(self.tmp.name,'分镜阅览.md');p.symlink_to(Path(self.tmp.name,'storyboard.json'))
        d=self.store.confirm(self.doc['sections'][0]['id'],0,'用户确认')
        self.assertIn('符号链接',d['_export_warning'])
        self.assertTrue(p.is_symlink())
    def test_global_brief_invalidates_prompts(self):
        d=self.add_derived();d['brief']='换视觉基调'
        d=self.store.update(d,d['revision']);self.assertTrue(all(x['status']=='stale' for x in d['prompts']))
    def test_source_change_invalidates_prompts(self):
        d=self.add_derived();d['source_text']='原文换了。'
        d=self.store.update(d,d['revision']);self.assertTrue(all(x['status']=='stale' for x in d['prompts']))
    def test_group_rename_invalidates_only_group(self):
        d=self.add_derived();d['sections'][0]['groups'][0]['title']='新的镜头组含义'
        d=self.store.update(d,d['revision']);self.assertTrue(all(x['status']=='stale' for x in d['prompts']))

if __name__=='__main__':unittest.main()
