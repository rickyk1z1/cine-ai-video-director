"""Deterministic paths for storyboard work and generated video media. Read-only."""
import argparse
import json
from pathlib import Path
import re


def component(value, label):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 80:
        raise ValueError(label + '须为非空稳定名称（不超过80字）')
    if value in ('.', '..') or re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.endswith(('.', ' ')):
        raise ValueError(label + '不能含路径分隔符、控制符或跨系统禁用字符')
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(label + '不能使用系统保留名称')
    return value


def paths(workspace_dir, *, project_root=None, work_id=None, run_id=None):
    workspace = Path(workspace_dir).expanduser().resolve()
    if project_root is None:
        if work_id is not None:
            raise ValueError('多作品共用目录时请明确项目根，再使用作品ID')
        video_root = workspace / '视频素材'
        scope = 'single_work'
    else:
        if work_id is None:
            raise ValueError('项目根下须提供稳定作品ID')
        project = Path(project_root).expanduser().resolve()
        video_root = project / '视频素材' / component(work_id, '作品ID')
        scope = 'project_work'
    candidate = video_root / '候选'
    if run_id is not None:
        candidate = candidate / component(run_id, '生成任务ID')
    return {'scope': scope, 'workspace': str(workspace), 'storyboard': str(workspace / 'storyboard.json'),
            'inputs': str(workspace / '制作输入'), 'process': str(workspace / '过程记录'),
            'preview_video': str(workspace / '过程记录'), 'video_root': str(video_root),
            'candidate_video': str(candidate), 'adopted_video': str(video_root / '采用')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, help='本作品分镜工作区')
    parser.add_argument('--project-root', help='明确的项目根；省略时按单作品工作区')
    parser.add_argument('--work-id', help='项目内稳定作品ID')
    parser.add_argument('--run-id', help='真实生成任务或批次标识；可省略')
    args = parser.parse_args()
    try:
        print(json.dumps(paths(args.directory, project_root=args.project_root, work_id=args.work_id,
                               run_id=args.run_id), ensure_ascii=False, indent=2))
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
