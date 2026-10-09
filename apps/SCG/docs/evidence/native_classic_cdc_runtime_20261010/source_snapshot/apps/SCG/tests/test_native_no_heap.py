import os
from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_no_heap import NativeNoHeap_FilesRender


def test_rejecting_newlib_heap_abi(tmp_path):
    origin=os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT')
    if not origin:
        pytest.skip('reviewed native sysmem input unavailable')
    source=(Path(origin)/'cube-f103-usb/Core/Src/sysmem.c').read_bytes()
    with pytest.raises(ValueError,match='source identity'):
        NativeNoHeap_FilesRender(source+b'\n')
    files=NativeNoHeap_FilesRender(source)
    for path,content in files.items():
        dest=tmp_path/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    compiler=shutil.which('gcc')
    if compiler is None:
        pytest.skip('Host GCC unavailable')
    (tmp_path/'test.c').write_text('''#include "native_no_heap.h"
#include <assert.h>
#include <stdint.h>
#include <errno.h>
int main(void)
{
    const ptrdiff_t requests[]={0,1,-1,PTRDIFF_MAX,PTRDIFF_MIN,1024,-1024};
    for (uint32_t index=0U;index<7U;index++)
    { errno=0;assert(_sbrk(requests[index])==(void *)-1 && errno==ENOMEM); }
    return 0;
}
''',encoding='utf-8')
    result=subprocess.run([compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic',
        '-Wconversion','-Wsign-conversion','-Wstrict-prototypes','-Wmissing-prototypes','-fanalyzer',
        '-I'+str(tmp_path/'Generated/Inc'),str(tmp_path/'Generated/Src/native_no_heap.c'),
        str(tmp_path/'test.c'),'-o',str(tmp_path/'test.exe')],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    run=subprocess.run([str(tmp_path/'test.exe')],capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stdout+run.stderr
