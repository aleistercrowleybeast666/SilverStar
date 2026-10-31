"""The emitted storage gate accepts each exact owner and still rejects ambiguity."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('sources,accepted', [
    (['FATFS/Target/sd_diskio.c'], True),
    (['HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c'], True),
    (['Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c'], True),
    ([], False),
    (['FATFS/Target/sd_diskio.c', 'HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c'], False),
    (['../FATFS/Target/sd_diskio.c'], False),
    (['unknown/FATFS/Target/sd_diskio.c'], False),
])
def test_exact_storage_diskio_owner_contract(tmp_path, sources, accepted):
    root = Path(__file__).resolve().parents[1]
    owner = root/'plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/host_contract.ps1'
    graph = tmp_path/'sources.mk'
    graph.write_text('C_SOURCES += \\\n'+''.join('  '+source+' \\\n' for source in sources), encoding='utf8')
    command = tmp_path/'validate.ps1'
    command.write_text('''param([string]$Owner,[string]$Graph)
. $Owner
try { HostContract_DiskioValidate -SourceGraph (Get-Content -LiteralPath $Graph -Raw); exit 0 }
catch { Write-Output $_.Exception.Message; exit 9 }
''', encoding='utf8')
    shell = shutil.which('powershell') or shutil.which('pwsh')
    assert shell, 'PowerShell is required to execute the emitted owner gate'
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(command), '-Owner', str(owner), '-Graph', str(graph)], capture_output=True, text=True, timeout=30)
    assert result.returncode == (0 if accepted else 9), result.stdout+result.stderr
    if not accepted:
        assert 'exactly one authoritative diskio' in result.stdout
