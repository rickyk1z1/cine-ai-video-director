"""Actual Store entrypoints must consume the same visual choice shown in the workbench."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import storyboard
import production

class VisualStyleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=storyboard.Store(self.tmp.name)
        d=storyboard.new_document('窗边植物科普')
        sh=storyboard.new_shot();sh.update(id='SH1',number='01',content='窗边一株幼苗。',duration=4)
        d['sections']=[dict(id='S1',title='幼苗',notes='',groups=[dict(id='G1',title='生长',notes='',shots=[sh])])]
        self.doc=self.store.create(d['title'],d)
    def action(self,command,source='conversation'):
        return self.store.workspace_action(command,self.store.read()['revision'],source=source)
    def select(self,source='workbench',**extra):
        command={'area':'style','choice':{'base_id':'clay','world_id':None,'tones':['温暖治愈'],'brief':'微缩黏土植物，保持可辨的叶片。','project_notes':'绿色叶片，浅色花盆。'},**extra}
        return self.action(command,source)
    def entry(self):
        return {'id':'entry','kind':'decision','title':'绘图','section_ids':['S1'],'shot_ids':['SH1'],
                'data':{'decision_type':'image_stage_entry','batch_id':'B1','selection_evidence':'开始做图'}}
    def test_new_project_defaults_to_visual_direction_and_blocks_atomic_image_entry(self):
        self.assertFalse(self.doc['_visual_style']['ready'])
        self.assertEqual(self.doc['_workflow']['scopes'][0]['next_actions'][0]['code'],'visual_style')
        before=self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'视觉定调'):
            self.store.transact({'confirmations':[{'section_id':'S1','evidence':'确认文字'}],'records':[self.entry()]},0)
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_workbench_choice_is_the_production_style_without_adopting_media(self):
        d=self.select()
        choice=d['workspace']['style_choice'];r=next(r for r in d['production']['records'] if r['id']==choice['record_id'])
        self.assertEqual(r['data']['style_choice_id'],choice['id'])
        self.assertEqual(r['data']['status'],'adopted')
        self.assertIn('绿色叶片',r['body'])
        self.assertEqual(d['_workflow']['phase'],0)
        self.assertEqual(d['production']['confirmations'],{})
        self.assertFalse(any(r['kind'] in ('asset','grid','result') for r in d['production']['records']))
        out=self.store.record(self.entry(),d['revision'])
        self.assertEqual(out['_workflow']['phase'],1)
    def test_dialogue_requires_true_evidence_and_presentation(self):
        with self.assertRaisesRegex(ValueError,'选择或跳过依据'):self.select(source='conversation')
        with self.assertRaisesRegex(ValueError,'已展示'):self.select(source='conversation',selection_evidence='用户选黏土')
        d=self.select(source='conversation',selection_evidence='用户看过工作台图鉴后选黏土',presentation_evidence='工作台已展示clay、puppet和cgtoon三组图')
        self.assertTrue(d['_visual_style']['ready'])
        self.assertEqual(d['workspace']['style_choice']['source'],'conversation')
        self.assertNotIn('用户在工作台',d['workspace']['style_choice']['selection_evidence'])
    def test_provided_reference_and_explicit_skip_do_not_force_gallery_choice(self):
        d=self.action({'area':'style','source':'provided','selection_evidence':'用户提供参考并要求沿用','choice':{'brief':'沿用用户提供的黑白建筑参考'}})
        self.assertEqual(d['workspace']['style_choice']['source'],'provided')
        # A separate skip is an explicit user decision, not a default.
        with self.assertRaisesRegex(ValueError,'依据'):self.action({'area':'style','op':'skip'})
        d=self.action({'area':'style','op':'skip','selection_evidence':'用户明确要求此次只做文字直投，不比较风格'})
        self.assertEqual(d['_visual_style']['status'],'skipped')
        self.assertEqual(self.store.record(self.entry(),d['revision'])['_workflow']['phase'],1)
    def test_recommendations_persist_without_selecting_or_advancing(self):
        d=self.action({'area':'style','op':'recommend','brief':'植物科普的材质比较','items':[{'id':'clay','reason':'用手作质感解释叶片'},{'id':'paper','reason':'层次明确'},{'id':'natural','reason':'展示自然材质'}]})
        self.assertEqual([i['id'] for i in self.store.current()['workspace']['style_recommendations']['items']],['clay','paper','natural'])
        self.assertFalse(d['_visual_style']['ready'])
        self.assertEqual(d['_workflow']['phase'],0)
    def test_bare_adopted_record_cannot_bypass_new_project_choice(self):
        d=self.store.record({'id':'plain','kind':'style','title':'口头大方向','body':'3D','section_ids':['S1'],'data':{'status':'adopted','adoption_evidence':'用户选3D'}},0)
        with self.assertRaisesRegex(ValueError,'视觉定调'):self.store.record(self.entry(),d['revision'])
    def test_style_can_be_selected_before_shots_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=storyboard.Store(tmp);d=store.create('建筑宣传片')
            d=store.workspace_action({'area':'style','choice':{'base_id':'natural','brief':'自然写实建筑'}},d['revision'],source='workbench')
            self.assertTrue(d['_visual_style']['ready'])
            self.assertEqual(d['production']['records'][0]['section_ids'],[])
    def test_new_assets_bind_style_and_style_change_marks_them_stale(self):
        d=self.select();d=self.store.confirm('S1',d['revision'],'确认文字')
        Path(self.tmp.name,'asset.png').write_bytes(b'asset-test-bytes')
        d=self.store.record({'id':'leaf','kind':'asset','title':'叶片','section_ids':['S1'],'shot_ids':['SH1'],'files':[{'path':'asset.png','role':'image'}],'data':{'asset_role':'prop','status':'candidate'}},d['revision'])
        asset=next(r for r in d['production']['records'] if r['id']=='leaf')
        self.assertIn(d['workspace']['style_choice']['record_id'],asset['depends_on'])
        d=self.action({'area':'style','choice':{'base_id':'paper','brief':'纸艺植物，保留叶片辨识度'}},'workbench')
        self.assertTrue(d['_record_states']['leaf']['stale'])
        self.assertEqual(Path(self.tmp.name,'asset.png').read_bytes(),b'asset-test-bytes')
    def test_legacy_style_is_visible_and_remains_usable(self):
        d=copy.deepcopy(self.doc);d.pop('workspace')
        style={'id':'legacy','kind':'style','title':'既有风格','body':'既有黑白建筑风格','section_ids':['S1'],'data':{'status':'adopted','adoption_evidence':'历史明确采用'}}
        production.put_record(d,style,Path(self.tmp.name));self.store.path.write_text(json.dumps(d))
        out=self.store.read()
        self.assertEqual(out['_visual_style']['status'],'inherited')
        self.assertEqual(out['_visual_style']['brief'],'既有黑白建筑风格')
        self.assertEqual(self.store.record(self.entry(),out['revision'])['_workflow']['phase'],1)
    def test_scoped_legacy_style_does_not_bind_unrelated_assets(self):
        d=copy.deepcopy(self.doc);d.pop('workspace')
        second=copy.deepcopy(d['sections'][0]);second['id']='S2';second['groups'][0]['id']='G2';second['groups'][0]['shots'][0]['id']='SH2';d['sections'].append(second)
        production.put_record(d,{'id':'style-one','kind':'style','title':'First scope','body':'First section direction','section_ids':['S1'],'data':{'status':'adopted','adoption_evidence':'OFFLINE legacy choice'}},Path(self.tmp.name))
        self.store.path.write_text(json.dumps(d))
        d=self.store.confirm('S2',d['revision'],'OFFLINE second-scope text confirmation')
        d=self.store.record({'id':'other-asset','kind':'asset','title':'Other section asset','section_ids':['S2'],'shot_ids':['SH2'],'data':{'asset_role':'prop','status':'candidate'}},d['revision'])
        self.assertNotIn('style-one',next(r for r in d['production']['records'] if r['id']=='other-asset')['depends_on'])

    def test_stale_style_editor_cannot_overwrite_new_conversation_choice(self):
        first=self.select();old_id=first['workspace']['style_choice']['id']
        self.select(source='conversation',selection_evidence='用户改成同一方向的另一说明',presentation_evidence='此前已看图')
        before=self.store.path.read_bytes()
        with self.assertRaises(storyboard.Conflict):
            self.action({'area':'style','expected_style_choice_id':old_id,'choice':{'base_id':'paper','brief':'旧页面未保存的纸艺草稿'}},'workbench')
        self.assertEqual(self.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()

