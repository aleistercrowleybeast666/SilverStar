"""Maintainer-only deterministic metadata extraction; never executes pack code.

Usage: python update_target_catalog.py OUTPUT F1.pdsc F4.pdsc C0.pdsc
Review input provenance/hash/license and resulting diff before committing. Not a
GSHC import path: arbitrary user PDSC files do not acquire memory permissions.
"""
from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET


def Extract(path):
    raw = path.read_bytes()
    assert len(raw) <= 8 * 1024 * 1024 and b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw
    root = ET.fromstring(raw)
    source = root.findtext('vendor') + '.' + root.findtext('name') + '.' + root.find('releases/release').get('version')
    devices = {}
    def walk(node, proc, memory, debug, depth):
        assert depth <= 8
        proc, memory, debug = dict(proc), dict(memory), dict(debug)
        processors = node.findall('processor')
        assert len(processors) <= 1, 'Multi-core PDSC needs reviewed capability handling'
        for item in processors: proc.update(item.attrib)
        for item in node.findall('debug'): debug.update(item.attrib)
        for item in node.findall('memory'):
            memory[item.get('id', item.get('name'))] = dict(item.attrib)
        children = [c for c in node if c.tag in ('family','subFamily','device','variant')]
        if not children and node.tag in ('device','variant'):
            name = node.get('Dvariant', node.get('Dname'))
            assert name and name.startswith('STM32')
            regions = []
            for key, item in memory.items():
                access = item.get('access', 'rwx' if 'RAM' in key.upper() else 'rx')
                kind = 'ram' if 'w' in access and 'RAM' in key.upper() else 'flash' if 'w' not in access else 'unknown'
                if kind != 'unknown': regions.append([kind, int(item['start'],0), int(item['size'],0)])
            ap = int(debug.get('__ap',debug.get('__apid','0')),0)
            assert proc.get('Dendian','Little-endian') == 'Little-endian'
            devices[name] = dict(core=proc['Dcore'], ap=ap, memory=regions, source=source)
        for child in children: walk(child, proc, memory, debug, depth+1)
    walk(root.find('devices'), {}, {}, {}, 0)
    return devices, dict(source=source, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                         url=f'https://www.keil.com/pack/{root.findtext("vendor")}.{root.findtext("name")}.pdsc',
                         license=root.findtext('license', 'See original pack license; metadata facts only'))


if __name__ == '__main__':
    targets, sources = {}, []
    for arg in sys.argv[2:]:
        devices, source = Extract(Path(arg))
        assert not set(targets) & set(devices)
        targets.update(devices); sources.append(source)
    Path(sys.argv[1]).write_text(json.dumps(dict(version=1,sources=sources,targets=targets),ensure_ascii=False,
                                         separators=(',',':'),sort_keys=True)+'\n',encoding='utf-8')
    print(len(targets), 'targets;', json.dumps(sources))
