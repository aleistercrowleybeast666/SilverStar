import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
records = []
patches = []
for name in ['PureINS', 'KF6', 'ESKF15', 'SF6']:
    old = ROOT / '.work/SF6_20261001_v1' / (name + '_v8') / 'Flight_Controller'
    new = OUT / (name + '_legacy_v1') / 'Flight_Controller'
    changed = []
    for path in sorted(old.rglob('*')):
        relative = path.relative_to(old)
        other = new / relative
        if not path.is_file() or 'build' in relative.parts or path.suffix.lower() not in ['.c', '.h', '.ld', '.s']:
            continue
        assert other.is_file(), str(relative)
        if path.read_bytes() != other.read_bytes():
            changed.append({'file': relative.as_posix(), 'old_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'new_sha256': hashlib.sha256(other.read_bytes()).hexdigest()})
            patches.extend(difflib.unified_diff(path.read_text(encoding='utf-8').splitlines(True), other.read_text(encoding='utf-8').splitlines(True), fromfile=name + '/v8/' + relative.as_posix(), tofile=name + '/integrated/' + relative.as_posix()))
    records.append({'name': name, 'changes': changed})
(OUT / 'generated_delta_from_v8.patch').write_text(''.join(patches), encoding='utf-8')
(OUT / 'generated_delta_from_v8.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps(records))
