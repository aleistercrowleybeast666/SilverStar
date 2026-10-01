from pathlib import Path
import shutil, importlib.util, os, json, contextlib
out = Path(__file__).parent.resolve()
source = out / 'candidate_a_v6/Ground_Station'
copy = out / 'ground_artifact_negative'
if copy.exists():
    raise SystemExit('fresh negative fixture required')
shutil.copytree(source, copy, ignore=shutil.ignore_patterns('analysis', 'ground-host'))
spec = importlib.util.spec_from_file_location('ground_gate', copy / 'Tools/check_ground.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
binary = copy / 'build/ground.bin'
original_bin = binary.read_bytes()
elf = copy / 'build/ground.elf'
original_elf = elf.read_bytes()
mapping = copy / 'build/ground.map'
original_map = mapping.read_text(encoding='utf-8')
results = []
for fault in ['binary', 'map', 'machine', 'stale']:
    if fault == 'binary':
        binary.write_bytes(bytes((original_bin[0] ^ 1,)) + original_bin[1:])
    elif fault == 'map':
        mapping.write_text(original_map.replace('build/Ground/Core/Src/ground_bridge.o', 'removed-object.o'), encoding='utf-8')
    elif fault == 'machine':
        elf.write_bytes(original_elf[:18] + bytes((3, 0)) + original_elf[20:])
    else:
        graph = json.loads((copy / 'Generated/ground_source_graph.json').read_text(encoding='utf-8'))
        os.utime(copy / graph['sources'][0], (elf.stat().st_mtime + 60, elf.stat().st_mtime + 60))
    with (out / ('artifact_negative_' + fault + '.log')).open('w', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log):
            try:
                module.Artifact_Check(copy, 'arm-none-eabi-')
            except ValueError as error:
                expected = {'binary':'BIN does not match', 'map':'object absent', 'machine':'ELF is not ARM', 'stale':'ELF older'}[fault]
                if expected not in str(error):
                    raise
                print('EXPECTED REJECTION:', error)
                results.append({'fault':fault,'expected_rejection':str(error)})
            else:
                raise RuntimeError('negative artifact was accepted: ' + fault)
    binary.write_bytes(original_bin)
    elf.write_bytes(original_elf)
    mapping.write_text(original_map, encoding='utf-8')
(out / 'artifact_negative_results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
