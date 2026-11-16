"""Archive auditable text evidence without firmware products or stale reattribution."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / '.work/platform-finish-20261116/boards'
DEST = Path(__file__).resolve().parent / 'runs'


def Digest_Get(raw):
    return hashlib.sha256(raw).hexdigest()


def Group_Write(name, paths):
    records = []
    for path in sorted(paths):
        raw = path.read_bytes()
        try:
            content = {'text_utf8': raw.decode('utf8')}
        except UnicodeDecodeError:
            content = {'raw_base64': base64.b64encode(raw).decode('ascii')}
        records.append({'source': path.relative_to(ROOT).as_posix(), 'bytes': len(raw),
                        'sha256': Digest_Get(raw), **content})
    raw = (json.dumps({'scope': name, 'records': records}, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(packed) >= 2 * 1024 * 1024:
        raise ValueError('Split evidence group; never change artifact gate: ' + name)
    output = DEST / (name + '.json.gz')
    output.write_bytes(packed)
    decoded = json.loads(gzip.decompress(output.read_bytes()))
    for original, row in zip(records, decoded['records'], strict=True):
        restored = row['text_utf8'].encode('utf8') if 'text_utf8' in row else base64.b64decode(row['raw_base64'])
        if Digest_Get(restored) != original['sha256'] or len(restored) != original['bytes']:
            raise ValueError('Evidence gzip readback mismatch')
    return {'file': output.name, 'bytes': len(packed), 'sha256': Digest_Get(packed),
            'record_count': len(records), 'uncompressed_bytes': sum(row['bytes'] for row in records),
            'readback_all_sha256_equal': True,
            'sources': [{'path': row['source'], 'sha256': row['sha256']} for row in records]}


def Main_Run():
    if DEST.exists():
        raise ValueError('Keep previous formal evidence')
    DEST.mkdir()
    groups = []
    top = [p for p in WORK.iterdir() if p.is_file() and p.suffix in ('.log', '.json', '.script', '.ssproject', '.py')
           and not p.name.startswith('duplicate-build')]
    groups.append(Group_Write('generation-diagnostics-and-regression', top))
    folders = [p for p in WORK.iterdir() if p.is_dir() and (
        p.name.endswith('-validation') or p.name in ('f103-probe-b', 'ground-review-j',
        'ground-negative-o', 'm3-negative-d', 'ground-workflow-o', 'ground-workflow-o-readable',
        'ssgs-workflow-final', 'm3-workflow-final', 'ssgs-workflow-current'))]
    for folder in sorted(folders):
        text_paths = [p for p in folder.rglob('*') if p.is_file() and p.suffix in ('.log', '.json')]
        if text_paths:
            groups.append(Group_Write(folder.name, text_paths))
        for screenshot in folder.glob('*.png'):
            target = DEST / (folder.name + '-' + screenshot.name)
            shutil.copy2(screenshot, target)
    for location in ('dist/pf1117-boards', 'dist/pf1117-boards-current'):
        folder = ROOT / location
        paths = [folder / 'delivery-receipt.json', *folder.glob('*/MANIFEST.json')]
        groups.append(Group_Write(folder.name + '-delivery', [p for p in paths if p.is_file()]))
    cleanup = DEST.parents[1] / 'delivery/board-duplicate-cleanup-inventory.json.gz'
    original_inventory = (WORK / 'duplicate-build-inventory.json').read_bytes()
    if gzip.decompress(cleanup.read_bytes()) != original_inventory:
        raise ValueError('Root formal cleanup inventory differs; do not silently deduplicate evidence')
    index = {'format': 'gzip UTF-8 JSON; each record preserves exact original bytes and SHA256',
        'hardware_tested': False, 'product_binaries_included': False, 'groups': groups,
        'deduplicated_cleanup_inventory': {'path': '../../delivery/board-duplicate-cleanup-inventory.json.gz',
            'uncompressed_sha256': Digest_Get(original_inventory), 'bytes': len(original_inventory)}}
    (DEST / 'index.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'groups': len(groups), 'records': sum(row['record_count'] for row in groups),
                      'compressed_bytes': sum(row['bytes'] for row in groups)}))


if __name__ == '__main__':
    Main_Run()
