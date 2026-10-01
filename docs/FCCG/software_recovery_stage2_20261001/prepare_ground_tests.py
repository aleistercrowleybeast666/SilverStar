import ast
import json
from pathlib import Path
root = Path(__file__).resolve().parents[2] / 'apps/FCCG'
payload = root / 'plugins/builtin/silverstar_core_ground_0_1_0/payload'
tests = payload / 'Tests/Host'
tests.mkdir(parents=True, exist_ok=True)
def strings(name):
    tree = ast.parse((root / 'tests' / name).read_text(encoding='utf-8'))
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
bounds = next(x for x in strings('test_ground_bridge_bounds.py') if '#include <assert.h>' in x)
(tests / 'ground_bridge_bounds.c').write_text(bounds, encoding='utf-8')
uart = strings('test_ground_pc_uart_dma.py')
(tests / 'uart_dma_main.h').write_text(next(x for x in uart if '#ifndef __MAIN_H' in x), encoding='utf-8')
(tests / 'uart_dma.c').write_text(next(x for x in uart if '#include <assert.h>' in x), encoding='utf-8')
usb = strings('test_ground_usb_cdc_ring.py')
(tests / 'usb_cdc_if.h').write_text(next(x for x in usb if '#ifndef __USBD_CDC_IF_H' in x), encoding='utf-8')
(tests / 'usb_cdc.c').write_text(next(x for x in usb if '#include <assert.h>' in x), encoding='utf-8')
manifest_path = payload.parent / 'plugin.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['payload']['roots'] = ['Ground', 'Tools', 'Tests/Host']
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
