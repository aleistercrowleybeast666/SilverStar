"""Review only changed Git blobs; reject accidental workspaces and build outputs."""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path, PurePosixPath

LIMIT = 2 * 1024 * 1024
CACHE_PARTS = {'.venv', 'venv', '__pycache__', '.pytest_cache', '.ruff_cache',
               '.work', '.qa', '.test-tmp', '.codex-remote-attachments', 'node_modules', 'dist'}
PRODUCT_SUFFIXES = {'.exe', '.dll', '.pyd', '.pyc', '.pyo', '.elf', '.o', '.obj',
                    '.whl', '.apk', '.class', '.zip', '.7z', '.bin'}


def Git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def Reasons(path, size):
    parts = PurePosixPath(path).parts
    reasons = []
    if any(part in CACHE_PARTS for part in parts):
        reasons.append('temporary workspace or environment')
    if 'build' in parts and not path.startswith('apps/SCG/src/silverstar_fccg/build/'):
        reasons.append('generated build tree')
    if PurePosixPath(path).suffix.lower() in PRODUCT_SUFFIXES:
        reasons.append('binary or archive product')
    if size > LIMIT:
        reasons.append(f'blob exceeds {LIMIT} bytes ({size})')
    return reasons


def Main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='base commit; empty/zero uses HEAD parent')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    root = Path(Git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
    if args.staged:
        diff = ['--cached']
        revision = ''
    else:
        base = args.base
        if not base or set(base) == {'0'}:
            parents = Git(root, 'rev-list', '--parents', '-n', '1', args.head).decode().split()
            base = parents[1] if len(parents) > 1 else '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        diff = [base, args.head]
        revision = args.head
    changed = Git(root, 'diff', '--no-renames', '--name-only', '-z', '--diff-filter=ACM', *diff)
    # Exceptions are exact files or narrowly owned fixture/vendor groups with an
    # explicit purpose in a reviewable file. They never allow workspace directories.
    policy_path = root / 'tools/repository_artifacts.json'
    policy = json.loads(policy_path.read_text(encoding='utf8')) if policy_path.exists() else []
    failures = []
    count = 0
    for raw in changed.split(b'\0'):
        if not raw:
            continue
        path = raw.decode('utf8')
        size = int(Git(root, 'cat-file', '-s', revision + ':' + path))
        reasons = Reasons(path, size)
        exceptions = [
            row for row in policy
            if row.get('reason') and fnmatch.fnmatchcase(path, row['path'])
        ]
        if exceptions and not any(part in CACHE_PARTS for part in PurePosixPath(path).parts):
            reasons = [reason for reason in reasons if reason != 'binary or archive product']
        if reasons:
            failures.append(f"{path}: {'; '.join(reasons)}")
        count += 1
    if failures:
        print('\n'.join(failures))
        print('FAIL: move generated outputs to the task workspace; '
              'retain necessary input provenance.')
        return 1
    print(f'PASS: {count} changed Git blobs reviewed; historical blobs were not reclassified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
