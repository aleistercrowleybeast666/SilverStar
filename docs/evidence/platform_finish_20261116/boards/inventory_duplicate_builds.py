"""Inventory only owned intermediate compiled bytes identical to sealed delivery."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / '.work/platform-finish-20261116/boards'
SUFFIXES = {'.o', '.d', '.su', '.i', '.s', '.elf', '.bin', '.map', '.hex', '.exe'}


def Digest_Get(raw):
    return hashlib.sha256(raw).hexdigest()


def Main_Run():
    output = WORK / 'duplicate-build-inventory.json'
    if output.exists():
        raise ValueError('Preserve previous inventory')
    delivery = ROOT / 'dist/pf1117-boards'
    seal = json.loads((delivery / 'delivery-receipt.json').read_text(encoding='utf8'))
    packages = {}
    for row in seal['packages']:
        archive = Path(row['zip']).resolve(strict=True)
        if Digest_Get(archive.read_bytes()) != row['zip_sha256']:
            raise ValueError('Protected archive changed')
        with zipfile.ZipFile(archive) as stream:
            manifest = json.loads(stream.read('MANIFEST.json'))
            if set(stream.namelist()) != set(manifest['files']) | {'MANIFEST.json'}:
                raise ValueError('Archive entry set differs')
            for name, item in manifest['files'].items():
                raw = stream.read(name)
                if len(raw) != item['bytes'] or Digest_Get(raw) != item['sha256']:
                    raise ValueError('Protected archive readback failed')
        packages[archive.name] = (row, manifest['files'])
    owned = [(WORK / ('candidate-' + label) / target,
              'SSFC1_0_SSGS1_0.zip', target)
             for label in ('c', 'd', 'e', 'f', 'g', 'i', 'j', 'k', 'l', 'm', 'n')
             for target in ('Flight_Controller', 'Ground_Station')]
    owned.append((ROOT / '.work/pf1117/ground-m3-c/Ground_Station', 'F103_E19_Ground.zip', 'Ground_Station'))
    rows, retained, missing = [], [], []
    for folder, archive_name, prefix in owned:
        build = folder / 'build'
        if not build.exists():
            missing.append(str(build))
            continue
        resolved = build.resolve(strict=True)
        if resolved != build.absolute() or not resolved.is_relative_to(ROOT / '.work'):
            raise ValueError('Unexpected owned build resolution')
        archive_row, manifest = packages[archive_name]
        for path in sorted(build.rglob('*')):
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('Aliased build entry rejected')
            if not path.is_file():
                continue
            relative = path.relative_to(folder).as_posix()
            member = prefix + '/' + relative
            stat = path.stat()
            record = {'path': str(path), 'bytes': stat.st_size,
                'sha256': Digest_Get(path.read_bytes()), 'file_id': stat.st_ino,
                'device': stat.st_dev, 'mtime_ns': stat.st_mtime_ns}
            expected = manifest.get(member)
            if (path.suffix.lower() in SUFFIXES and expected and expected['bytes'] == stat.st_size
                    and expected['sha256'] == record['sha256']):
                rows.append({**record, 'owned_build_root': str(build), 'archive': archive_row['zip'],
                    'archive_sha256': archive_row['zip_sha256'], 'member': member})
            else:
                retained.append(record)
    result = {'purpose': 'Proposed exact duplicate compiled subset only; this script does not delete',
        'owned_roots': [str(folder / 'build') for folder, _, _ in owned], 'missing_roots': missing,
        'protected_packages': [row for row, _ in packages.values()],
        'candidate_rows': rows, 'candidate_count': len(rows), 'candidate_bytes': sum(row['bytes'] for row in rows),
        'retained_rows': retained, 'retained_count': len(retained),
        'retained_bytes': sum(row['bytes'] for row in retained)}
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: result[key] for key in ('candidate_count', 'candidate_bytes', 'retained_count', 'retained_bytes')}))


if __name__ == '__main__':
    Main_Run()
