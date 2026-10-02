"""Select the declared Common owner from the explicitly chosen FCCG checkout."""
import json
from pathlib import Path


def FccgCommon_RootGet(root: Path) -> Path:
    owners = []
    for manifest_path in (root / 'plugins/builtin').glob('*/plugin.json'):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('type') != 'core' or manifest.get('class') != 'flight_controller_core':
            continue
        common = manifest_path.parent / 'payload/Common'
        if (common / 'Inc/silverstar_assert.h').is_file() and (common / 'Src/silverstar_assert.c').is_file():
            owners.append(common)
    if len(owners) != 1:
        raise ValueError(f'Explicit FCCG source requires one declared Common owner; found {len(owners)}')
    return owners[0]
