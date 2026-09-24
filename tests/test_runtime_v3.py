"""Real loopback lifecycle checks in disposable skill and project directories."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import storyboard


class RuntimeV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.install=root/'skill'
        self.install.mkdir()
        for folder in ('scripts','assets'):
            shutil.copytree(storyboard.ROOT/folder,self.install/folder,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(storyboard.ROOT/'SKILL.md',self.install/'SKILL.md')
        self.project=root/'project'
        storyboard.Store(self.project).create('Isolated runtime check')
        self.servers=[]
        self.addCleanup(self.stop_known_servers)

    def cli(self,command,project=None):
        result=subprocess.run([sys.executable,str(self.install/'scripts/storyboard.py'),command,
                               '--directory',str(project or self.project)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def remember(self,result):
        health=storyboard.service_request(result['url'],'/api/health')
        self.servers.append((result['url'],health))
        return health

    def stop_known_servers(self):
        # Cleanup only identities read from servers started by this test.
        for url,known in reversed(self.servers):
            try:
                health=storyboard.service_request(url,'/api/health')
                if (health.get('instance'),health.get('directory'))!=(known.get('instance'),known.get('directory')):
                    continue
                token=storyboard.service_request(url,'/api/session')['token']
                storyboard.service_request(url,'/api/shutdown',{},token)
                for _ in range(30):
                    try:storyboard.service_request(url,'/api/health')
                    except (OSError,ValueError):break
                    time.sleep(.05)
            except (OSError,ValueError,KeyError):
                pass

    def test_open_reuse_disk_build_restart_and_stop(self):
        before=(self.project/'storyboard.json').read_bytes()
        first=self.cli('open');old=self.remember(first)
        self.assertFalse(first['reused']);self.assertTrue(old['current'])
        again=self.cli('open')
        self.assertTrue(again['reused']);self.assertEqual(again['url'],first['url'])
        self.assertEqual(storyboard.service_request(first['url'],'/api/health')['instance'],old['instance'])
        css=self.install/'assets/style.css'
        css.write_text(css.read_text()+'\n/* isolated build change */\n')
        self.assertFalse(storyboard.service_request(first['url'],'/api/health')['current'])
        restarted=self.cli('open');new=self.remember(restarted)
        self.assertFalse(restarted['reused']);self.assertTrue(restarted['restarted'])
        self.assertEqual(restarted['url'],first['url'])
        self.assertNotEqual(new['instance'],old['instance']);self.assertNotEqual(new['build_id'],old['build_id'])
        self.assertTrue(new['current'])
        self.assertTrue(self.cli('stop')['stopped'])
        with self.assertRaises(OSError):storyboard.service_request(restarted['url'],'/api/health')
        self.assertFalse(self.cli('stop')['stopped'])
        self.assertEqual((self.project/'storyboard.json').read_bytes(),before)

    def test_stop_requires_matching_directory_and_instance(self):
        started=self.cli('open');health=self.remember(started)
        manifest=self.project/'.storyboard-server.json'
        original=json.loads(manifest.read_text())
        manifest.write_text(json.dumps({**original,'instance':'not-this-instance'}))
        self.assertFalse(self.cli('stop')['stopped'])
        self.assertEqual(storyboard.service_request(started['url'],'/api/health')['instance'],health['instance'])
        other=self.project.parent/'other-project'
        storyboard.Store(other).create('Unrelated project')
        (other/'.storyboard-server.json').write_text(json.dumps(original))
        self.assertFalse(self.cli('stop',other)['stopped'])
        self.assertEqual(storyboard.service_request(started['url'],'/api/health')['instance'],health['instance'])
        manifest.write_text(json.dumps(original))
        self.assertTrue(self.cli('stop')['stopped'])

    def test_open_does_not_replace_or_stop_a_foreign_service(self):
        original=self.cli('open');health=self.remember(original)
        other=self.project.parent/'other-project'
        storyboard.Store(other).create('Independent project')
        shutil.copy2(self.project/'.storyboard-server.json',other/'.storyboard-server.json')
        opened=self.cli('open',other);new=self.remember(opened)
        self.assertFalse(opened['reused']);self.assertFalse(opened['restarted'])
        self.assertNotEqual(opened['url'],original['url'])
        self.assertEqual(new['directory'],str(other.resolve()))
        self.assertEqual(storyboard.service_request(original['url'],'/api/health')['instance'],health['instance'])
        self.assertTrue(self.cli('stop',other)['stopped'])
        self.assertEqual(storyboard.service_request(original['url'],'/api/health')['instance'],health['instance'])

    def test_copied_cli_creates_reads_and_opens_a_blank_project(self):
        other=self.project.parent/'blank-workspace'
        created=self.cli('create',other)
        self.assertEqual(created['sections'],[]);self.assertEqual(created['revision'],0)
        opened=self.cli('open',other);health=self.remember(opened)
        self.assertEqual(health['directory'],str(other.resolve()))
        self.assertEqual(self.cli('read',other)['id'],created['id'])
        self.assertEqual(storyboard.service_request(opened['url'],'/api/document')['id'],created['id'])
        self.assertTrue(self.cli('stop',other)['stopped'])

    def test_simultaneous_open_calls_share_one_service(self):
        command=[sys.executable,str(self.install/'scripts/storyboard.py'),'open','--directory',str(self.project)]
        processes=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(3)]
        results=[]
        try:
            for process in processes:
                stdout,stderr=process.communicate(timeout=20)
                self.assertEqual(process.returncode,0,stderr)
                result=json.loads(stdout);results.append(result);self.remember(result)
            self.assertEqual(len({r['url'] for r in results}),1)
            self.assertEqual(sum(not r['reused'] for r in results),1)
            self.assertTrue(self.cli('stop')['stopped'])
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.wait(timeout=5)
                process.stdout.close();process.stderr.close()


if __name__=='__main__':unittest.main()
