"""Real frame API with an explicit corrupt-metadata callee fault seam."""
import ctypes as ct
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'apps/SCG/plugins/builtin'
PROTOCOL=BASE/'silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG'
COMMON=BASE/'silverstar_core_0_1_0/payload/Common'


@pytest.fixture(scope='module',params=['-O0','-O2'])
def codec(request,tmp_path_factory):
    output=tmp_path_factory.mktemp('metadata_bounds'+request.param)
    sources=[PROTOCOL/'Src/sslog_protocol.c',COMMON/'Src/silverstar_assert.c',
             Path(__file__).with_name('fixtures')/'sslog_metadata_bounds.c']
    compiler=shutil.which('gcc');assert compiler,'Actual GCC required'
    target=output/'bounds.dll'
    command=[compiler,'-std=c11',request.param,'-Wall','-Wextra','-Werror','-Wpedantic','-shared',
        '-I'+str(PROTOCOL/'Inc'),'-I'+str(COMMON/'Inc'),*map(str,sources),'-o',str(target)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=120)
    (output/'compile.json').write_text(json.dumps(dict(command=command,exit_code=run.returncode,
        stdout=run.stdout,stderr=run.stderr,compiler=subprocess.check_output([compiler,'--version'],text=True),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}),indent=2))
    assert run.returncode==0,run.stdout+run.stderr
    result=ct.CDLL(str(target));result.Test_MetadataBounds.argtypes=[ct.c_uint32,ct.c_uint32,ct.POINTER(ct.c_uint32)]
    return result


@pytest.mark.parametrize('size',[0,257,65535])
@pytest.mark.parametrize('decode',[0,1])
def test_bad_metadata_rejected_before_publication_or_capacity_overrun(codec,size,decode):
    result=(ct.c_uint32*4)();codec.Test_MetadataBounds(size,decode,result)
    assert list(result)==[6 if decode else 3,0,0,0xBEEF]
