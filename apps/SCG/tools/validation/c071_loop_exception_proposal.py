"""Prepare/test an UNAUTHORIZED diagnostic-only exact C071 loop proposal.

Never changes the owning checker or a generated validation target. Writes an
isolated new directory, including a reviewable patch and complete test logs.
Positive proposal tests are not production gate or firmware acceptance results.
"""
from pathlib import Path
import argparse,difflib,hashlib,json,shutil,subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--usb',type=Path,required=True)
parser.add_argument('--uart',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
inputs={'usb_cdc':args.usb.resolve(),'uart':args.uart.resolve()}
output=args.output.resolve()
if output.exists() and any(output.iterdir()):raise ValueError('proposal output must be new/empty')
for root in inputs.values():
    if root==output or root.is_relative_to(output) or output.is_relative_to(root):raise ValueError('disjoint proposal output required')
output.mkdir(parents=True,exist_ok=True)
main_path='Platform/STM32C0/Src/main.c'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
contracts={}
for mode,root in inputs.items():
    main=(root/main_path).read_text(encoding='utf-8')
    lines=[i+1 for i,line in enumerate(main.splitlines()) if line.strip()=='while (1)']
    if len(lines)!=1 or 'SilverStarAssert_Fail' not in main:raise ValueError('unreviewed main')
    contracts[mode]={'path':main_path,'function':'main','line':lines[0],'sha256':sha(root/main_path),'body':'if (GroundBridge_Process(HAL_GetTick()) != GROUND_BRIDGE_OK) { Error_Handler(); }'}
baseline=(inputs['usb_cdc']/'Tools/check_power_of_ten.ps1').read_text(encoding='utf-8')
if baseline!=(inputs['uart']/'Tools/check_power_of_ten.ps1').read_text(encoding='utf-8'):raise ValueError('different owning gates')
helper='''# PROPOSAL ONLY: requires explicit approval of both exact main digests.
function Test-PowerTenReviewedC071SchedulerLine {
    param([System.IO.FileInfo]$File, [string]$Line, [int]$LineNumber)
    if (($TargetKind -ne 'Ground') -or
        ((Get-PowerTenRelativePath $File.FullName) -ne 'Platform/STM32C0/Src/main.c') -or
        ($Line -notmatch '^\\s*while\\s*\\(\\s*1\\s*\\)\\s*$')) { return $false }
    $graphPath = Join-Path $repoRoot 'Generated/ground_source_graph.json'
    if (-not (Test-Path -LiteralPath $graphPath -PathType Leaf)) { return $false }
    $graph = Get-Content -LiteralPath $graphPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (($graph.experimental_standalone_mcu -ne 'STM32C071FBP6') -or
        ($graph.complete_cube_import -ne $false) -or
        ($graph.defines -notcontains 'STM32C071xx') -or
        ($graph.mcu_flags -notcontains '-mcpu=cortex-m0plus')) { return $false }
    $reviewed = @{
        'usb_cdc' = @{ Line = __USB_LINE__; Sha256 = '__USB_SHA__' }
        'uart' = @{ Line = __UART_LINE__; Sha256 = '__UART_SHA__' }
    }
    if (-not $reviewed.ContainsKey([string]$graph.pc_interface)) { return $false }
    $contract = $reviewed[[string]$graph.pc_interface]
    if ($LineNumber -ne $contract.Line) { return $false }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = [System.BitConverter]::ToString(
            $hasher.ComputeHash([System.IO.File]::ReadAllBytes($File.FullName))).Replace('-', '').ToLowerInvariant()
    } finally { $hasher.Dispose() }
    return ($digest -eq $contract.Sha256)
}

'''
for label,mode in (('USB','usb_cdc'),('UART','uart')):
    helper=helper.replace('__'+label+'_LINE__',str(contracts[mode]['line'])).replace('__'+label+'_SHA__',contracts[mode]['sha256'])
anchor='$files = Get-FirstPartyCFiles\n'
call='''        $diagnostics = Get-PatternDiagnostics -File $file -Lines $lines `
            -Pattern $rule.Pattern'''
new_call=call+''' -Approved {
                param($candidateFile, $line, $lineNumber)
                return (($rule.Name -eq 'finite while/do loop') -and
                    (Test-PowerTenReviewedC071SchedulerLine $candidateFile $line $lineNumber))
            }'''
if baseline.count(anchor)!=1 or baseline.count(call)!=1:raise ValueError('unreviewed checker layout')
proposed=baseline.replace(anchor,helper+anchor).replace(call,new_call)
patch=''.join(difflib.unified_diff(baseline.splitlines(True),proposed.splitlines(True),fromfile='a/apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1',tofile='b/apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1'))
(output/'UNAUTHORIZED-proposal.patch').write_text(patch,encoding='utf-8')
(output/'UNAUTHORIZED-reviewed-loop-contracts.json').write_text(json.dumps(contracts,indent=2),encoding='utf-8')
results=[]
cases=[('baseline-usb','usb_cdc','baseline',1),('proposal-usb','usb_cdc','positive',0),('proposal-uart','uart','positive',0),('changed-main','usb_cdc','changed-main',1),('other-file-loop','uart','other-loop',1),('other-part','uart','other-part',1),('wrong-transport','usb_cdc','wrong-transport',1)]
for name,mode,change,expected in cases:
    root=inputs[mode];test=output/name
    for directory in ('Common','Devices','Generated','Ground','Platform'):
        for path in (root/directory).rglob('*'):
            if not path.is_file() or path.suffix not in ('.c','.h','.json'):continue
            dest=test/path.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    shutil.copyfile(root/'Makefile',test/'Makefile')
    linker=json.loads((root/'Generated/ground_source_graph.json').read_text(encoding='utf-8'))['linker_script']
    (test/linker).parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/linker,test/linker)
    (test/'Tools').mkdir()
    (test/'Tools/check_power_of_ten.ps1').write_text(baseline if change=='baseline' else proposed,encoding='utf-8')
    if change=='changed-main':
        p=test/main_path;p.write_text(p.read_text(encoding='utf-8')+'\nvoid Unauthorized_Loop(void) { while (1) { } }\n',encoding='utf-8')
    if change=='other-loop':(test/'Platform/Unauthorized.c').write_text('void Unauthorized_Loop(void) { while (1) { } }\n',encoding='utf-8')
    if change in ('other-part','wrong-transport'):
        p=test/'Generated/ground_source_graph.json';g=json.loads(p.read_text(encoding='utf-8'))
        if change=='other-part':g['experimental_standalone_mcu']='STM32F103C8'
        else:g['pc_interface']='uart'
        p.write_text(json.dumps(g),encoding='utf-8')
    command=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(test/'Tools/check_power_of_ten.ps1'),'-TargetKind','Ground']
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    log=output/(name+'.log');log.write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode!=expected or 'POWER10_CONTRACT_REVIEW|NOT_PROVEN' not in result.stdout:
        raise ValueError('unexpected diagnostic proposal result: '+name+' exit '+str(result.returncode))
    if expected==1 and 'finite while/do loop violation' not in result.stdout:raise ValueError('negative not rejected by loop gate: '+name)
    results.append({'case':name,'expected_exit':expected,'actual_exit':result.returncode,'log_sha256':sha(log),'authorization':'NOT AUTHORIZED; diagnostic proposal only'})
    print('PASS diagnostic case',name,'expected exit',expected,flush=True)
(output/'proposal-results.json').write_text(json.dumps({'contracts':contracts,'baseline_sha256':hashlib.sha256(baseline.encode()).hexdigest(),'patch_sha256':sha(output/'UNAUTHORIZED-proposal.patch'),'results':results,'scope':'no production gate/target changes; NOT an acceptance pass'},indent=2),encoding='utf-8')
