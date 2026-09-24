"""Portable output locations must be predictable and side-effect free."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import media_paths


class MediaPathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_project_work_and_run_keep_generated_media_outside_storyboard(self):
        project = self.base / '项目'; workspace = project / '分镜' / '作品甲'
        result = media_paths.paths(workspace, project_root=project, work_id='work-a', run_id='run-001')
        self.assertEqual(Path(result['candidate_video']), (project / '视频素材/work-a/候选/run-001').resolve())
        self.assertEqual(Path(result['adopted_video']), (project / '视频素材/work-a/采用').resolve())
        self.assertEqual(Path(result['inputs']), (workspace / '制作输入').resolve())
        self.assertEqual(Path(result['preview_video']), (workspace / '过程记录').resolve())
        self.assertFalse(project.exists())

    def test_projectless_workspace_uses_its_own_video_directory(self):
        workspace = self.base / '一次独立短片'
        result = media_paths.paths(workspace)
        self.assertEqual(Path(result['candidate_video']), (workspace / '视频素材/候选').resolve())
        self.assertEqual(Path(result['adopted_video']), (workspace / '视频素材/采用').resolve())
        self.assertFalse(workspace.exists())

    def test_rejects_ambiguous_or_unsafe_identity(self):
        bad = ('../other', 'a/b', 'a\\b', 'CON', '.hidden.', '', ' leading', 'a:b', 'bad\nname')
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                media_paths.paths(self.base, project_root=self.base, work_id=value)
        with self.assertRaises(ValueError):media_paths.paths(self.base, work_id='two-works')
        with self.assertRaises(ValueError):media_paths.paths(self.base, project_root=self.base)
        with self.assertRaises(ValueError):media_paths.paths(self.base, project_root=self.base, work_id='work', run_id='../../escape')

    def test_cli_returns_same_layout_without_writes(self):
        workspace = self.base / 'work'; project = self.base / 'project'
        cli = str(Path(media_paths.__file__))
        returned = json.loads(subprocess.check_output([sys.executable, cli, '--directory', str(workspace),
            '--project-root', str(project), '--work-id', 'A', '--run-id', 'run-1']))
        self.assertEqual(returned, media_paths.paths(workspace, project_root=project, work_id='A', run_id='run-1'))
        self.assertFalse(workspace.exists());self.assertFalse(project.exists())

if __name__ == '__main__':unittest.main()
