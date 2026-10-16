"""Read actual unmodified frames emitted by both SCG Host backend fixtures.

Run after test_kf6_horizon_backend.py and test_eskf15_horizon_backend.py, with
SILVERSTAR_HORIZON_TRACE_ROOT set to that invocation's fresh pytest directory.
These are CPU fixture frame streams, not onboard logs or a production opening.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import zlib

import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.catalog import RecordLayout
from silverstar_flp.decoder_profiles.fusion_horizon_records import (
    RECORDS, FusionHorizonLayout_Validate, FusionHorizonRecords_Validate,
)


def test_both_actual_backends_wire_boundaries(tmp_path):
    supplied = os.environ.get('SILVERSTAR_HORIZON_TRACE_ROOT')
    if not supplied:
        pytest.skip('Explicit fresh SCG backend trace root required; no synthetic replacement')
    root = Path(supplied).resolve()
    paths = sorted(root.glob('*backend_horizon*/case*.frames'))
    assert len(paths) == 50, 'Require both actual backends, O0/O2, twelve common and ESKF owned-state scenarios'
    layouts = {int(row['id'], 0): RecordLayout.FromDocument(row, 0) for row in RECORDS.values()}
    for layout in layouts.values():
        FusionHorizonLayout_Validate(layout)
    receipts = []
    for path in paths:
        data = path.read_bytes(); before = hashlib.sha256(data).hexdigest()
        records, cursor = [], 0
        while cursor < len(data):
            sync, version, kind, size, sequence, timestamp, flags = struct.unpack_from('<IBBHIQI', data, cursor)
            assert sync == 0x31474c46 and size <= 256
            total = 24 + size + 4; assert cursor + total <= len(data)
            assert zlib.crc32(data[cursor:cursor + total - 4]) == struct.unpack_from('<I', data, cursor + total - 4)[0]
            if kind in layouts:
                layout = layouts[kind]; assert layout.record_version == version
                records.append(DecodedRecord(kind, layout.name, version, size, sequence, timestamp, flags,
                    layout.Decode(data[cursor + 24:cursor + 24 + size]), cursor))
            cursor += total
        dataset = SimpleNamespace(Records_Get=lambda name: tuple(r for r in records if r.record_name == name))
        algorithm = 1 if path.parent.name.startswith('kf_') else 2
        evidence = FusionHorizonRecords_Validate(dataset, algorithm_id=algorithm, horizon_us=30000)
        scenario = int(path.stem.removeprefix('case'))
        expected_fault = scenario in (3, 4, 5, 8) or (algorithm == 2 and scenario == 12)
        assert ('fusion_horizon_fault_recorded' in evidence.replay_blockers) == expected_fault
        if not expected_fault:
            assert not evidence.replay_blockers
            expected_count = 1 if scenario in (9, 10) else (8 if scenario in (1, 2) else 4)
            assert len(evidence.completions) == expected_count
        if scenario == 11:
            assert len(evidence.completions) == 4
            assert all(record.payload['quality_scale'] > 1 for record in evidence.requests)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        receipts.append(dict(path=str(path), sha256=before, algorithm=algorithm, scenario=scenario,
            requests=len(evidence.requests), completions=len(evidence.completions),
            statuses=len(evidence.statuses), pending=len(evidence.pending), blockers=evidence.replay_blockers))
    (tmp_path/'actual_backend_wire_receipt.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
