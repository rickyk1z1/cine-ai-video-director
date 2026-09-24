"""Sound plan versus whole-video bans, without treating scoped or quoted speech as policy."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import production
import storyboard
import test_v3_workflow as fixtures


class SoundConsistencyTests(unittest.TestCase):
    def issues(self,roles,prompt,implementation='native'):
        scope={'video_count':1,'evidence':'一部独立完整影片'}
        doc={'production':{'records':[{'id':'R','data':{'output_scope':scope}}]}}
        record={'data':{'output_scope':scope,'production_path_decision_id':'R','sound_plan':{'policy':'single_video',
                'tracks':[{'role':role,'implementation':implementation,'description':'本片声音安排'} for role in roles]},
                'audio_capability':{'native_music':True,'evidence':'isolated specification fixture'},'prompt':prompt}}
        return production.sound_issues(doc,record)

    def test_global_music_and_voice_bans_are_conflicts(self):
        cases=[('music','全片不生成音乐。'),('dialogue','全片不生成对白。'),
               ('narration','整个视频不要旁白。'),('dialogue','本次生成禁止人声。'),
               ('music','声音要求：不生成背景音乐。'),('dialogue','声音：禁止任何对白。'),
               ('music','No music.'),('dialogue','Throughout the video, no dialogue.'),
               ('narration','Audio: do not generate narration.'),('music','# 视频\n\n不生成音乐。'),
               ('music','本片静音。')]
        for role,prompt in cases:
            with self.subTest(role=role,prompt=prompt):self.assertTrue(self.issues([role],prompt))

    def test_combined_bans_map_to_each_exact_role(self):
        prompt='全片禁止音乐、对白和旁白。'
        for role in ('music','dialogue','narration'):
            with self.subTest(role=role):self.assertTrue(self.issues([role],prompt))
        self.assertEqual(self.issues(['narration'],'全片禁止对白。'),[])
        self.assertEqual(self.issues(['dialogue'],'全片禁止旁白。'),[])
        self.assertEqual(self.issues(['music'],'采用无人声配乐。'),[])

    def test_scoped_and_exceptional_directives_do_not_become_global(self):
        cases=[(['music'],'开头没有音乐，结尾加入配乐。'),
               (['dialogue'],'镜头1：\n无对白。\n镜头2：演员开始说话。'),
               (['music'],'0–3秒无音乐，3–8秒加入音乐。'),
               (['dialogue'],'背景人物没有对白，主角讲解。'),
               (['music'],'全片不生成音乐，片尾除外。'),
               (['music'],'No music except during the ending.'),
               (['music'],'Shot 1:\nNo music.\nShot 2: music begins.'),
               (['dialogue'],'第1段：无对白；第2段：保留台词。'),
               (['music'],'# 镜头1\n\n不生成音乐。\n\n# 镜头2\n配乐响起。'),
               (['dialogue'],'镜头一：\n无对白。\n镜头二：保留台词。')]
        for roles,prompt in cases:
            with self.subTest(prompt=prompt):self.assertEqual(self.issues(roles,prompt),[])
        # An explicit whole-video ban still applies after local shot instructions.
        self.assertTrue(self.issues(['dialogue'],'镜头1展示产品。\n全片禁止对白。'))

    def test_quoted_double_negative_and_extra_voice_are_not_bans(self):
        cases=['演员说：“全片不生成对白。”随后继续讲解。','人物说："No dialogue."',
               '不要禁止对白。','不要求全片无对白。','全片不生成额外对白。',
               '不重新生成对白，使用既定录音。','保留对白，不新增旁白。']
        for prompt in cases:
            with self.subTest(prompt=prompt):self.assertEqual(self.issues(['dialogue'],prompt),[])
        self.assertEqual(self.issues(['music'],'不要禁止音乐。'),[])

    def test_external_or_absent_track_remains_valid(self):
        self.assertEqual(self.issues(['music'],'全片不生成音乐。','external'),[])
        self.assertEqual(self.issues(['dialogue'],'全片不生成对白。','none'),[])
        self.assertEqual(self.issues([],'全片不生成音乐或对白。'),[])
        self.assertEqual(self.issues(['sfx'],'不生成音乐，保留脚步音效。'),[])

    def test_prepare_rejects_contradiction_without_mutation_then_accepts_fix(self):
        fixture=fixtures.WorkflowV3Tests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        t=fixture.t;package=fixture.v3_package();doc=t.store.read()
        scope={'video_count':1,'evidence':'隔离测试：两镜一次完整生成'}
        route=next(r for r in doc['production']['records'] if r['id']=='PATH')
        route['data']['output_scope']=scope;t.store.record(route,doc['revision'])
        package['data']['output_scope']=scope
        package['data']['sound_plan']={'policy':'single_video','tracks':[{'role':'music','implementation':'native','description':'本片采用的音乐'}]}
        package['data']['audio_capability']={'native_music':True,'evidence':'isolated specification fixture'}
        before=t.store.path.read_bytes();revision=t.store.read()['revision']
        with self.assertRaisesRegex(storyboard.Conflict,'禁止音乐'):
            t.store.prepare(package,revision)
        self.assertEqual(before,t.store.path.read_bytes())
        prompt=package['data']['prompt'].replace('不生成音乐','配以已定音乐')
        package['data']['prompt']=prompt;package['data']['prompt_review']['prompt']=prompt
        result=t.store.prepare(package,revision)
        self.assertEqual(result['issues'],[])

if __name__=='__main__':unittest.main()
