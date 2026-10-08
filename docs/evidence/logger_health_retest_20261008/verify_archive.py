"""Verify exact evidence bytes and normalized source equivalence to a commit."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--commit')
args = parser.parse_args()
root = Path(__file__).resolve().parent
repo = root.parents[2]
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
for relative, expected in manifest['files'].items():
    path = root / relative
    contents = path.read_bytes()
    assert len(contents) == expected['bytes'], relative
    assert hashlib.sha256(contents).hexdigest() == expected['sha256'], relative
    if args.commit:
        stored = subprocess.check_output(['git', 'show', args.commit + ':' + path.relative_to(repo).as_posix()], cwd=repo)
        assert contents == stored, relative
revision = json.loads((root / 'source_revision.json').read_text(encoding='utf-8'))
for relative, expected in revision['owner_and_test_inputs'].items():
    contents = (subprocess.check_output(['git', 'show', args.commit + ':' + relative], cwd=repo)
                if args.commit else (repo / relative).read_bytes())
    text = contents.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    assert hashlib.sha256(text.encode()).hexdigest() == expected['normalized_sha256'], relative
print(json.dumps(dict(evidence_files=len(manifest['files']), source_inputs=len(revision['owner_and_test_inputs']),
                      commit=args.commit, byte_exact_evidence=True, normalized_source_equivalent=True), indent=2))
