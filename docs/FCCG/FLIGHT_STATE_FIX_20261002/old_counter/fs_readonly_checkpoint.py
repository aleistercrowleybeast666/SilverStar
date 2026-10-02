from pathlib import Path
import ast, collections, hashlib, json, sys
sys.dont_write_bytecode = True
repo = Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
generated = Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002\.work\imu_final\Flight_Controller')
hardware = Path(r'D:\stm32_project\SilverStar_HardwareBaseline_20261001\FieldIntegration_DualBench_20261002_081145\IMUStartup_Validated_20261002_121336')
out = repo / '.work/fs_readonly'
out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(repo / 'apps/GSHC'))
from protocol.air import parse_air_frame
functions = {
 'Modules/Src/telemetry_service.c': ['TelemetryService_Process', 'TelemetryService_StreamSend', 'TelemetryService_NavigationSend', 'TelemetryService_NavigationHealthSend', 'TelemetryService_NavigationFrameSend', 'TelemetryService_ImuQuantizedGet', 'TelemetryService_PreflightDisable'],
 'Modules/Src/estimator_task.c': ['Estimator_GetLatestSnapshot'],
 'Protocol/Src/air_protocol.c': ['Air_FlightStateBuild'],
 'Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c': ['Sx1281Transport_Send'],
 'Devices/Telemetry/SX1281/Src/sx1281_device.c': ['Lora_TxQueuePushClass', 'Lora_PacketAirtimeMs'],
 'System/Inertial/Src/system_inertial.c': ['SystemInertial_LatestGet'],
}
records = []
for relative, names in functions.items():
 p = generated / relative
 if not p.exists():
  records.append({'file': relative, 'missing': True}); continue
 lines = p.read_text(encoding='utf8').splitlines()
 for name in names:
  found = False
  for start, line in enumerate(lines):
   if name + '(' not in line or not line.startswith(('static ', 'uint8_t ', 'SystemDeviceResult ', 'AirBuildResult ', 'void ')):
    continue
   brace = start
   while brace < len(lines) and '{' not in lines[brace] and ';' not in lines[brace]: brace += 1
   if brace == len(lines) or '{' not in lines[brace]: continue
   depth = 0
   for end in range(brace, len(lines)):
    depth += lines[end].count('{') - lines[end].count('}')
    if depth == 0: break
   text = '\n'.join(lines[start:end+1]) + '\n'
   (out / (name + '.c')).write_text(text, encoding='utf8')
   records.append({'file': relative, 'function': name, 'line': start+1, 'source_sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'function_sha256': hashlib.sha256(text.encode()).hexdigest()})
   found = True; break
  if not found: records.append({'file': relative, 'function': name, 'not_found': True})
counts = []
for p in sorted((hardware / 'FullFlow/GSHC_Data/logs').glob('*.jsonl')):
 before = hashlib.sha256(p.read_bytes()).hexdigest()
 kinds, types, parsed, gsp = (collections.Counter() for _ in range(4))
 errors = []
 for number, line in enumerate(p.read_text(encoding='utf8').splitlines(), 1):
  r = json.loads(line); kinds[r.get('kind', '')] += 1
  if r.get('kind') == 'AIR_RAW':
   b = bytes.fromhex(r['air_hex']); types[f'{b[0]:02x}/{len(b)}'] += 1
   try: parsed[type(parse_air_frame(b)).__name__] += 1
   except Exception as e: errors.append({'line': number, 'error': repr(e)})
  if r.get('kind') == 'GSP_FRAME' and r.get('msg_type') == 2:
   b = bytes.fromhex(r['payload_hex']); gsp[f'{b[3]:02x}/{b[2]}'] += 1
 after = hashlib.sha256(p.read_bytes()).hexdigest()
 assert before == after
 counts.append({'file': str(p), 'sha256_before': before, 'sha256_after': after, 'kinds': dict(kinds), 'raw_types': dict(types), 'actual_gshc_parser': dict(parsed), 'raw_gsp_radio_types': dict(gsp), 'parse_errors': errors})
(out / 'runtime_counts.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
(out / 'function_manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
print(json.dumps({'out': str(out), 'functions': records, 'runtime': counts}, ensure_ascii=False, indent=2))
