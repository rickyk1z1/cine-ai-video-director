"""Keep known project identity out of reusable skill instructions."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_portability import scan


class PortabilityTests(unittest.TestCase):
    def test_skill_sources_have_no_known_project_identity(self):
        self.assertEqual(scan(), [])

    def test_scan_finds_project_identity_in_new_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / 'sample.md'
            sample.write_text('本项目由 Ricky 在专用画布操作。', encoding='utf-8')
            self.assertEqual({kind for _, _, kind in scan([sample])},
                             {'ambiguous_project_rule', 'personal_or_project_name'})


if __name__ == '__main__':
    unittest.main()
