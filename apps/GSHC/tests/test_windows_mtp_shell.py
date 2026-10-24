"""Exercise the actual Windows COM copy implementation on synthetic local files."""
import base64
import json
import os
from pathlib import Path
import subprocess
from threading import Event
import pytest
from services.windows_mtp import WindowsMtp, MtpOperationResult


@pytest.mark.skipif(os.name!='nt',reason='Windows COM copy helper')
def test_real_shell_copy_completes_and_collision_never_replaces(tmp_path):
    source=tmp_path/'source';target=tmp_path/'target';back=tmp_path/'back'
    for p in (source,target,back):p.mkdir()
    data=bytes(range(256))*8192
    (source/'synthetic.bin').write_bytes(data)
    (target/'occupied.bin').write_bytes(b'KEEP ORIGINAL')
    helper=Path(__file__).parents[1]/'services/windows_mtp_copy.cs'
    def literal(p):return "'"+str(p).replace("'","''")+"'"
    code=f"""
$ErrorActionPreference='Stop'
Add-Type -Path {literal(helper)}
[SilverStar.MtpCopy]::Copy({literal(source/'synthetic.bin')}, {literal(target)}, 'synthetic.bin')
$shell=New-Object -ComObject Shell.Application
$remote=$shell.NameSpace({literal(target)}).ParseName('synthetic.bin')
$sink=$shell.NameSpace({literal(back)}).Self
[SilverStar.MtpCopy]::CopyShellItems($remote, $sink, 'synthetic.bin')
[SilverStar.MtpCopy]::Copy({literal(source/'synthetic.bin')}, {literal(target)}, 'occupied.bin')
$missingFailed=$false
try {{ [SilverStar.MtpCopy]::Copy({literal(source/'missing.bin')}, {literal(target)}, 'missing.bin') }}
catch {{ $missingFailed=$true }}
@{{ missingFailed=$missingFailed; complete=$true }} | ConvertTo-Json -Compress
"""
    script=tmp_path/'copy.ps1';script.write_text(code,encoding='utf-8-sig')
    exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    encoded=base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    run=subprocess.run([str(exe),'-NoProfile','-NonInteractive','-Sta','-EncodedCommand',encoded],
                       capture_output=True,timeout=30)
    assert run.returncode==0,run.stderr.decode(errors='replace')
    assert json.loads(run.stdout)['missingFailed']
    assert (back/'synthetic.bin').read_bytes()==data
    assert (target/'occupied.bin').read_bytes()==b'KEEP ORIGINAL'
    assert (source/'synthetic.bin').read_bytes()==data


@pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell helper')
def test_real_helper_reports_phase_without_touching_phone():
    reply=WindowsMtp()._process(dict(operation='copy',destination='invalid'),Event())
    assert reply.result is MtpOperationResult.Failed
    assert 'stage=validate_destination' in reply.detail and 'HRESULT=' in reply.detail
    assert reply.diagnostics['stage']=='validate_destination'
    assert reply.diagnostics['exceptions'][0]['type']


def _shell_source(source, request):
    # Same framed stdin protocol as the product; no device or Shell instance.
    loader=('[ScriptBlock]::Create([Text.Encoding]::UTF8.GetString('
            '[Convert]::FromBase64String([Console]::In.ReadLine()))).Invoke()')
    encoded=base64.b64encode(loader.encode('utf-16-le')).decode('ascii')
    exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    run=subprocess.run([str(exe),'-NoProfile','-NonInteractive','-Sta','-EncodedCommand',encoded],
        input=base64.b64encode(source.encode('utf-8'))+b'\n'+json.dumps(request).encode(),
        capture_output=True,timeout=20)
    assert run.returncode==0,run.stderr.decode(errors='replace')
    return json.loads(run.stdout.decode('utf-8-sig'))


FAKE_FOLDERS=r'''
function FakeFolder($path, $children) {
    $f=[pscustomobject]@{Self=$null; Children=@($children)}
    $f | Add-Member -MemberType ScriptMethod -Name Items -Value { @($this.Children) }
    $f.Self=[pscustomobject]@{Path=$path; Name='same display name'; IsFolder=$true; IsFileSystem=$false; GetFolder=$f}
    return $f
}
$devicePath='::{20D04FE0-3AEA-1069-A2D8-08002B30309D}\device#{6AC27878-A6FA-4155-BA85-F98F491D4F33}'
$destination=$devicePath+'\Storage\Logs'
$leaf=FakeFolder $destination @()
$storage=FakeFolder ($devicePath+'\Storage') @($leaf.Self)
$device=FakeFolder $devicePath @($storage.Self)
$root=FakeFolder 'This PC' @($device.Self)
$fakeShell=[pscustomobject]@{Root=$root}
$fakeShell | Add-Member -MemberType ScriptMethod -Name NameSpace -Value {
    param($value)
    if ($value -is [int] -and $value -eq 17) { return $this.Root }
    return $null
}
'''


@pytest.mark.skipif(os.name!='nt',reason='PowerShell virtual namespace simulation')
@pytest.mark.parametrize('case',['exact','wrong_identity','ambiguous'])
def test_virtual_picker_path_rebinds_by_exact_parent_identity(case):
    text=(Path(__file__).parents[1]/'services/windows_mtp.ps1').read_text(encoding='utf-8')
    functions=text[:text.index('$copySubmitted = $false')]
    change={'exact':'','wrong_identity':"$leaf.Self.Path=$devicePath+'\\Storage\\Other'",
            'ambiguous':'$storage.Children=@($leaf.Self,$leaf.Self)'}[case]
    result=_shell_source(functions+FAKE_FOLDERS+change+r'''
$legacyNull=$null -eq $fakeShell.NameSpace($destination)
try {
    $resolved=Destination_Resolve $fakeShell $destination
    @{legacyNull=$legacyNull; resolved=([string]$resolved.Self.Path -ceq $destination)} | ConvertTo-Json -Compress
} catch {
    @{legacyNull=$legacyNull; resolved=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress
}
''',{})
    assert result['legacyNull'] is True
    assert result['resolved'] is (case=='exact')
    if case!='exact':assert 'identity' in result['error']


@pytest.mark.skipif(os.name!='nt',reason='PowerShell structured diagnostics simulation')
def test_nested_exception_keeps_actual_com_hresult_and_type():
    text=(Path(__file__).parents[1]/'services/windows_mtp.ps1').read_text(encoding='utf-8')
    fake=r'''
$fakeShell=[pscustomobject]@{}
$fakeShell | Add-Member ScriptMethod NameSpace {
    throw [InvalidOperationException]::new('outer identity resolver',
        [Runtime.InteropServices.COMException]::new('synthetic COM detail', -2147467259))
}
'''
    text=fake+text.replace('New-Object -ComObject Shell.Application','$fakeShell')
    destination='::{20D04FE0-3AEA-1069-A2D8-08002B30309D}\\device#{6AC27878-A6FA-4155-BA85-F98F491D4F33}\\Storage'
    result=_shell_source(text,dict(operation='copy',destination=destination,name='SilverStar_export_synthetic',
                                  files=[{},{}]))
    assert result['status']=='failed'
    chain=result['diagnostics']['exceptions']
    assert any(x['type']=='System.InvalidOperationException' for x in chain)
    assert chain[-1]['type']=='System.Runtime.InteropServices.COMException'
    assert chain[-1]['hresult']=='0x80004005'
    assert 'locked' not in result['detail']
