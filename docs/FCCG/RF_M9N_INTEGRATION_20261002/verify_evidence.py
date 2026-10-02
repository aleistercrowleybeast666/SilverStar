from pathlib import Path
import json,hashlib,gzip,zipfile
repo=Path(r'D:\python_software\SilverStar\.work\RfM9nIntegration_20261002')
docs=repo/'docs/FCCG/RF_M9N_INTEGRATION_20261002'
m=json.loads((docs/'FINAL_MANIFEST.json').read_text(encoding='utf8'))
def sha(b): return hashlib.sha256(b).hexdigest()
for name,v in m['artifacts'].items(): assert sha(Path(v['path']).read_bytes())==v['sha256'],name
for name,v in m['logs'].items():
 b=(docs/'logs'/name).read_bytes(); assert sha(b)==v['gzip_sha256']
 assert sha(gzip.decompress(b))==v['raw_sha256']
counter=m['software_conflict_counterexample']
assert sha(gzip.decompress((docs/'logs/sw_counter__neo_m9n_device.c.gz').read_bytes()))==counter['source_sha256']
assert sha(gzip.decompress((docs/'logs/sw_counter__test_neo_m9n_device.c.gz').read_bytes()))==counter['test_sha256']
archive=Path(m['source_firmware_archive']['path']); assert sha(archive.read_bytes())==m['source_firmware_archive']['sha256']
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for name,v in m['artifacts'].items(): assert sha(z.read('Flight_Controller/build/FCCG/SilverStar_F407/Release/'+name))==v['sha256']
 for v in m['source_owner_generated']: assert sha(z.read('Flight_Controller/'+v['generated']))==v['sha256']
 count=len(z.namelist())
assert len(m['rf_base_files_unchanged'])==24
assert not any(r['exit'] for r in m['gates'] if not r['name'].startswith('Debug'))
assert '.ccm' not in (docs/'host-sections.txt').read_text(encoding='utf8')
print('Verified: artifacts, gzip logs, counterexample snapshots, ZIP CRC and source/firmware equality, all24 RF files, Host ordinary BSS; ZIP entries='+str(count))
print('Archive sha256='+m['source_firmware_archive']['sha256'])
