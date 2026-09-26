#!/usr/bin/env python3
"""Flag project identity in reusable skill instructions and executable code."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKED = [ROOT / 'AGENTS.md', ROOT / 'SKILL.md', *ROOT.glob('agents/*.yaml'),
           *ROOT.glob('references/**/*.md'),
           *ROOT.glob('references/**/*.json'),
           *(p for p in ROOT.glob('assets/**/*') if p.suffix in ('.js','.html','.css')),
           *(p for p in ROOT.glob('scripts/**/*.py') if p.name != Path(__file__).name),
           *(p for p in ROOT.glob('tests/**/*.py') if p.name != 'test_portability.py')]
PATTERNS = {
    'personal_or_project_name': re.compile('|'.join(('Ri' + 'cky', '永' + '乐有礼', '宴' + '南都', '小' + '渡'))),
    'project_identifier': re.compile('|'.join(('project' + 'Id', 'canvas' + 'Id', 'agent_thread' + '_id', r'项目[0-9０-９]+'))),
    'personal_path': re.compile('/Users/' + r'[^/\s]+/'),
    'ambiguous_project_rule': re.compile('本' + '项目'),
}


def scan(paths=CHECKED):
    issues = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    issues.append((str(path), number, name))
    return issues


if __name__ == '__main__':
    found = scan()
    for path, line, kind in found:
        print(f'{path}:{line}: {kind}')
    print(f'checked {len(CHECKED)} files; {len(found)} project-identity findings')
    raise SystemExit(bool(found))
