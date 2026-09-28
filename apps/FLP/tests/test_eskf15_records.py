from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.catalog import RecordCatalog
from silverstar_flp.decoder_profiles.eskf15_records import Eskf15Records_Adapt


def _Parts():
    upper = np.eye(15)[np.triu_indices(15)]
    return tuple(
        DecodedRecord(
            0x22,
            "ESKF15_FULL_P_PART",
            1,
            144,
            index,
            1_000_000,
            0,
            dict(
                snapshot_id=10,
                epoch=2,
                source_id=0,
                calibration_generation=3,
                algorithm_id=2,
                phase=1,
                part_index=index,
                part_count=4,
                offset=index * 30,
                count=30,
                values=tuple(upper[index * 30 : (index + 1) * 30]),
            ),
            index * 168,
        )
        for index in range(4)
    )


def test_covariance_parts_identity_missing_duplicate_and_psd():
    parts = _Parts()
    channels, errors = Eskf15Records_Adapt({"ESKF15_FULL_P_PART": parts})
    assert not errors
    series = channels["eskf15.recorded.covariance.upper_triangle"]
    assert series.valid.tolist() == [True]
    np.testing.assert_array_equal(series.values[0], np.eye(15)[np.triu_indices(15)])
    for bad in (
        parts[:3],
        (*parts, parts[0]),
        (*parts[:3], replace(parts[3], timestamp_us=1_000_001)),
        (*parts[:3], replace(parts[3], payload={**parts[3].payload, "snapshot_id": 11})),
        (*parts[:3], replace(parts[3], payload={**parts[3].payload, "epoch": 3})),
        (*parts[:3], replace(parts[3], payload={**parts[3].payload, "phase": 0})),
    ):
        channels, errors = Eskf15Records_Adapt({"ESKF15_FULL_P_PART": bad})
        assert not channels and errors


@pytest.mark.skipif(
    not os.environ.get("SILVERSTAR_FCCG_ROOT"),
    reason="requires explicitly selected current FCCG protocol source",
)
def test_actual_c_record_codec_catalog_and_fragment_roundtrip(tmp_path):
    root = Path(os.environ["SILVERSTAR_FCCG_ROOT"])
    protocol = root / "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG"
    common = root / "plugins/builtin/silverstar_core_0_0_12/payload/Common/Inc"
    source = tmp_path / "codec.c"
    source.write_text(
        r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sslog_protocol.h"
#include "silverstar_assert.h"
int main(int argc, char **argv)
{
    FlightLogRecord record, decoded;
    uint8_t wire[300];
    uint16_t length, read;
    uint32_t sequence;
    FILE *file;
    assert(argc == 2);
    _Static_assert(sizeof(FlightLogEskf15StateRecord) <=
        sizeof(FlightLogEstimatorRecord), "slot growth");
    _Static_assert(sizeof(FlightLogEskf15CovariancePartRecord) <=
        sizeof(FlightLogEstimatorRecord), "slot growth");
    file=fopen(argv[1], "wb"); assert(file);
    for (unsigned part=0; part<4; part++) {
        memset(&record,0,sizeof(record)); record.record_type=FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART;
        record.timestamp_us=1000000;
        FlightLogEskf15CovariancePartRecord *p=&record.payload.eskf15_full_p_part;
        p->snapshot_id=10; p->epoch=2; p->source_id=0; p->calibration_generation=3;
        p->algorithm_id=2; p->phase=1; p->part_index=part;
        p->part_count=4; p->count=30; p->offset=part*30;
        unsigned at=0;
        for(unsigned row=0; row<15; row++) for(unsigned col=row; col<15; col++,at++) {
            if(at>=p->offset && at<p->offset+30U) p->values[at-p->offset]=(row==col)?1.0f:0.0f;
        }
        assert(FlightLog_RecordSerialize(&record,part,wire,sizeof(wire),&length)==FLIGHT_LOG_SERIALIZE_RESULT_OK);
        assert(length==172);
        assert(FlightLog_RecordDeserialize(wire,length,&decoded,&sequence,&read)==FLIGHT_LOG_DESERIALIZE_RESULT_OK);
        assert(sequence==part && read==length);
        assert(decoded.payload.eskf15_full_p_part.part_index==part);
        assert(fwrite(wire,1,length,file)==length);
    }
    for (unsigned type=0x21; type<=0x27; type++) {
        memset(&record,0,sizeof(record)); record.record_type=(FlightLogRecordType)type;
        assert(FlightLog_RecordSerialize(&record,type,wire,sizeof(wire),&length)==FLIGHT_LOG_SERIALIZE_RESULT_OK);
        assert(FlightLog_RecordDeserialize(wire,length,&decoded,&sequence,&read)==FLIGHT_LOG_DESERIALIZE_RESULT_OK);
        assert((unsigned)decoded.record_type==type);
        wire[30]^=1;
        assert(FlightLog_RecordDeserialize(wire,length,&decoded,&sequence,&read)==FLIGHT_LOG_DESERIALIZE_RESULT_BAD_CRC);
    }
    assert(fclose(file)==0);
    printf("seven C codecs; fullP four parts; CRC rejection; slot=%zu\n",sizeof(FlightLogRecord));
    return 0;
}
""",
        encoding="utf8",
    )
    executable = tmp_path / "codec.exe"
    command = [
        shutil.which("gcc"),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-O2",
        "-I",
        str(protocol / "Inc"),
        "-I",
        str(common),
        str(common.parent / "Src/silverstar_assert.c"),
        str(source),
        str(protocol / "Src/sslog_records.c"),
        str(protocol / "Src/sslog_protocol.c"),
        "-o",
        str(executable),
    ]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    built = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert built.returncode == 0, built.stderr
    output = tmp_path / "parts.bin"
    result = subprocess.run([str(executable), str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (tmp_path / "codec_result.txt").write_text(result.stdout, encoding="utf8")
    catalog = RecordCatalog.FromDocument(
        json.loads((protocol / "schema/sslog_schema.json").read_text(encoding="utf8"))
    )
    layout = catalog.Layout_Get(0x22, 1)
    raw = output.read_bytes()
    records = []
    for index in range(4):
        payload = raw[index * 172 + 24 : index * 172 + 168]
        decoded = layout.Decode(payload)
        records.append(replace(_Parts()[index], payload=decoded))
    channels, errors = Eskf15Records_Adapt({"ESKF15_FULL_P_PART": tuple(records)})
    assert not errors
    np.testing.assert_array_equal(
        channels["eskf15.recorded.covariance.upper_triangle"].values,
        [np.eye(15)[np.triu_indices(15)]],
    )
