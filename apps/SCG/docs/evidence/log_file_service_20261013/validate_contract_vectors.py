from pathlib import Path
import hashlib
import json
import re
import zlib

root = Path(__file__).resolve().parents[1]
service = json.loads((root / "contracts/log_file_service_v1.json").read_text(encoding="utf-8"))
schema = json.loads((root / "contracts/session_export_v1.schema.json").read_text(encoding="utf-8"))
manifest = json.loads((root / "contracts/session_export_v1.golden.json").read_text(encoding="utf-8"))
data = bytes.fromhex(service["golden"]["file_bytes_hex"])
assert len(data) == service["golden"]["size"] == manifest["files"][0]["size_bytes"]
assert f"{zlib.crc32(data):08X}" == service["golden"]["crc32"]
assert hashlib.sha256(data).hexdigest() == manifest["files"][0]["sha256"]
assert set(schema["required"]) == set(manifest)
assert manifest["schema_version"] == schema["properties"]["schema_version"]["const"]
item = schema["properties"]["files"]["items"]
assert set(item["required"]) == set(manifest["files"][0])
pattern = item["properties"]["path"]["pattern"]
accepted = ["logs/flight.sslog", "session-1.jsonl", "decoders/exact.ssdecoder"]
rejected = ["", ".", "..", "/absolute", "../escape", "logs/../escape", "logs/./x", "C:/x", "logs\\x", "a//b"]
assert all(re.fullmatch(pattern, name) for name in accepted)
assert all(not re.fullmatch(pattern, name) for name in rejected)
report = {"status": "PASS", "scope": "JSON parsing, cross-contract golden CRC/size/SHA256 and declared path-pattern vectors; not a full JSON Schema engine validation", "accepted_paths": accepted, "rejected_paths": rejected}
target = root / "apps/SCG/docs/evidence/log_file_service_20261013/contract_validation.json"
target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
