import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
frozen = ROOT / '.work/SoftwareCandidates_20261002_Single_v1'
formal = ROOT / 'docs/FCCG/sf6_stage3_20261002/FinalSingleEvidence_v8'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
index = json.loads((frozen / 'freeze_index.json').read_text(encoding='utf-8'))
resources = json.loads((formal / 'resources_v8_exact.json').read_text(encoding='utf-8'))
result = {'firmware_source_commit': '170f1cb55daedf8e8d308a7bc845b2fa5b79d102', 'freeze_evidence_commit': '5d6d12bab617f003d9721a2df024e78448f7c53f', 'scope': 'original immutable v8 single-sensor legacy-layout Delay10 candidates; excludes auto/Baro/GroundMulti', 'minimum_clock': 'NOT MEASURED; no DWT/hardware evidence, no MHz inferred', 'physical_ram_total_is_not_DMA_capacity': True, 'resources_v8': [], 'candidates': []}
for row in resources:
    total = row['main SRAM']['used'] + row['CCMRAM']['used']
    result['resources_v8'].append({**row, 'physical_ram_total_bytes': total})
assert [row['physical_ram_total_bytes'] for row in result['resources_v8']] == [127016, 157760, 164384, 145720]
for item in index:
    name = item['name']
    directory = frozen / (name + '_Delay10')
    project = ROOT / '.work/SF6_20261001_v1' / (name + '_v8')
    build = project / 'Flight_Controller/build/FCCG/SilverStar_F407/Release'
    zip_path = frozen / (name + '_Delay10.zip')
    assert sha(zip_path) == item['zip_sha256'] == sha(formal / zip_path.name)
    record = {'name': name, 'generation_root': str(project), 'generation_flight_root': str(project / 'Flight_Controller'), 'frozen_root': str(directory), 'frozen_decoder': str(directory / 'SS_0_5_TEST_4.ssdecoder'), 'zip': {'path': str(zip_path), 'formal_path': str(formal / zip_path.name), 'bytes': zip_path.stat().st_size, 'sha256': sha(zip_path)}, 'artifacts': {}}
    with zipfile.ZipFile(zip_path) as archive:
        for suffix in ['elf', 'bin']:
            file_name = 'SilverStar_0_1_1.' + suffix
            candidate = directory / 'Firmware' / file_name
            generated = build / file_name
            expected = item['firmware_sha256'][file_name]
            assert sha(candidate) == sha(generated) == expected
            entries = [entry for entry in archive.namelist() if entry.endswith('/Firmware/' + file_name)]
            assert len(entries) == 1, entries
            assert hashlib.sha256(archive.read(entries[0])).hexdigest() == expected
            record['artifacts'][suffix] = {'frozen_path': str(candidate), 'generated_path': str(generated), 'zip_entry': entries[0], 'bytes': candidate.stat().st_size, 'sha256': expected}
    result['candidates'].append(record)
(OUT / 'single_candidates_identity.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
