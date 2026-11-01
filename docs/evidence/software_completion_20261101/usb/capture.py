"""Retain actual generic USB logs and deduplicated compiled source evidence."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / '.work/0.1.3-software-completion-20261101'


def Main():
    inventory = []

    def Copy(source, destination):
        data = source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        inventory.append({'source': str(source), 'retained': destination.relative_to(HERE).as_posix(),
                          'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})

    for epoch in ('generic-before-v1', 'generic-after-v1'):
        source_root = WORK / 'usb' / epoch
        target = HERE / epoch
        for source in sorted(source_root.iterdir()):
            if source.is_file() and source.suffix in ('.json', '.log'):
                Copy(source, target / source.name)
        for part in ('f103', 'f407'):
            native = source_root / 'native' / part
            for name in ('lifecycle-integration.json', 'kit-sha256.json', 'receipt.json',
                         'integration.json', 'usb-adaptation.json', 'assertion-owner.json',
                         'Makefile', 'LICENSE-SilverStar.txt', 'Generated/usb_transport_source_graph.json'):
                Copy(native / name, target / part / name)
            graph = json.loads((native / 'Generated/usb_transport_source_graph.json').read_text(encoding='utf8'))
            selected = [Path(row['compiled']) for row in graph['sources'] if Path(row['compiled']).is_relative_to(native)]
            selected += sorted((native / 'Inc').glob('*.h'))
            selected += sorted((native / 'Native').rglob('*.patch'))
            source_map = []
            for source in selected:
                data = source.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                destination = HERE / 'source-objects' / (digest + source.suffix)
                if not destination.exists():
                    Copy(source, destination)
                source_map.append({'source': str(source), 'retained': destination.relative_to(HERE).as_posix(),
                                   'sha256': digest})
            (target / part / 'source-map.json').write_text(json.dumps(source_map, indent=2) + '\n', encoding='utf8')
            original = Path('D:/Codex_Work/2026-10-08/task/usb-validation') / ('cube-' + part + '-usb')
            for name in ('License.md', 'Package_license.md'):
                if (original / name).is_file():
                    Copy(original / name, HERE / 'native-licenses' / part / name)
    for epoch in ('generic-ep0-before-v1', 'generic-ep0-after-v1', 'generic-user-owner-v1'):
        for suffix in ('.log', '.exit'):
            Copy(WORK / ('usb-' + epoch + suffix), HERE / (epoch + suffix))
        test_root = WORK / 'usb' / epoch
        for receipt in test_root.rglob('control-receipt.json'):
            part = json.loads(receipt.read_text(encoding='utf8'))['part']
            for source in receipt.parent.iterdir():
                if source.name in ('control.c', 'compile.log', 'control-receipt.json'):
                    Copy(source, HERE / epoch / part / source.name)
    for epoch in ('generic-before-v1', 'generic-after-v1'):
        for suffix in ('.log', '.exit'):
            Copy(WORK / ('usb-' + epoch + suffix), HERE / (epoch + suffix))
    (HERE / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf8')
    print('Retained', len(inventory), 'records;', sum(row['bytes'] for row in inventory), 'bytes')


if __name__ == '__main__':
    Main()
