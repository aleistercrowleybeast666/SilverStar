"""Private native timer probe gates; no Ground/EP0 acceptance is represented."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
from check_native_ground import Artifact_Check
from ground_artifact_contract import _DependencyPaths_Get


def ConfigurationDependencies_Validate(root,graph,contract):
    root=root.resolve()
    selected=(root/contract['usb_config']['derived']).resolve()
    clock_header=(root/'HardwareGenerated/NativeClassicCdc'/contract['clock']['clock_header']).resolve()
    for build in ('build','build/analysis'):
        consumers=0
        for source in graph['sources']:
            obj=root/build/Path(source).with_suffix('.o')
            dependencies=_DependencyPaths_Get(root,obj.with_suffix('.d'),obj)
            configs=[p.resolve() for p in dependencies if p.name=='usbd_conf.h']
            if configs:
                if configs!=[selected]:
                    raise ValueError('Native USB compile selected an unreviewed config: '+source)
                consumers+=1
            if source=='Generated/Src/native_clock_port.c' and clock_header not in [p.resolve() for p in dependencies]:
                raise ValueError('Native timer port did not compile its reviewed kernel-clock header')
        if consumers==0:
            raise ValueError('Native explicit USB config has no actual compiled consumer')
    print('PASS normal/analyzer CPP dependencies select the actual reviewed timer and explicit USB headers')


def Architecture_Check(root):
    root=root.resolve()
    graph=json.loads((root/'Generated/ground_source_graph.json').read_text())
    contract=json.loads((root/'Generated/native_probe_contract.json').read_text())
    if graph.get('native_timer_probe') is not True or contract['clock']['port']!='tim1':
        raise ValueError('Native timer probe contract missing')
    make=(root/'Makefile').read_text().replace('\\\n',' ')
    for key,var in [('sources','C_SOURCES'),('asm_sources','ASM_SOURCES')]:
        match=re.search(r'^'+var+r' := (.*)$',make,re.M)
        if match is None or match[1].split()!=graph[key] or len(set(graph[key]))!=len(graph[key]):
            raise ValueError('Native timer probe graph differs from Make')
    compiled=graph['sources']+graph['asm_sources']
    for path in compiled+graph['include_dirs']+[graph['linker_script']]:
        resolved=(root/path).resolve()
        if not resolved.is_relative_to(root) or not resolved.exists():
            raise ValueError('Native timer probe path lacks root ownership')
    prefix='HardwareGenerated/NativeClassicCdc/'
    for path,digest in contract['original_sha256'].items():
        resolved=(root/prefix/path).resolve()
        if not resolved.is_relative_to(root) or hashlib.sha256(resolved.read_bytes()).hexdigest()!=digest:
            raise ValueError('Native timer original changed')
    for original,derived in contract['source_replacements'].items():
        if original in compiled or derived not in compiled:
            raise ValueError('Native timer replacement has duplicate/missing owner')
    for path,digest in contract['compiled_owned_sha256'].items():
        if path not in graph['sources'] or hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Native timer compiled owner changed')
    cfg=contract['usb_config']
    if (graph['include_dirs'][0]!=cfg['derived'].rsplit('/',1)[0] or
            hashlib.sha256((root/cfg['derived']).read_bytes()).hexdigest()!=cfg['derived_sha256']):
        raise ValueError('Native explicit USB config owner changed')
    linker=contract['linker']
    if graph['linker_script']!=linker['derived'] or hashlib.sha256((root/linker['derived']).read_bytes()).hexdigest()!=linker['derived_sha256']:
        raise ValueError('Native timer linker derivative changed')
    if any(path.endswith('/sysmem.c') or path.startswith(('Ground/','Devices/','Platform/Src')) for path in compiled):
        raise ValueError('Native timer probe has a heap or unclaimed Ground/port payload')
    if 'Generated/Src/native_no_heap.c' not in compiled or graph['required_link_symbols']!=['_sbrk'] or '-Wl,-u,_sbrk' not in make:
        raise ValueError('Native timer rejecting heap owner missing')
    print('PASS private timer probe source graph, immutable originals and unique timer/config/heap/linker owners')
    print('Ground runtime, EP0, semantic critical-contract review, stack/WCET and hardware: NOT PROVEN')
    return graph


def ProbeArtifact_Check(root,prefix):
    Artifact_Check(root,prefix,architecture_check=Architecture_Check)
    contract=json.loads((root/'Generated/native_probe_contract.json').read_text())
    graph=json.loads((root/'Generated/ground_source_graph.json').read_text())
    ConfigurationDependencies_Validate(root,graph,contract)
    StrongOwners_Validate(root,prefix,contract)


def StrongOwners_Validate(root,prefix,contract):
    for build in ('build','build/analysis'):
        command=[prefix+'nm','-n',str(root/build/'native.elf')]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if result.returncode!=0:raise ValueError('Native timer linked symbol read failed')
        text=(root/build/'native.map').read_text()
        for symbol,source in contract['required_symbol_owners'].items():
            entry=re.findall(r'(?m)^([\da-fA-F]+)\s+T\s+'+re.escape(symbol)+r'$',result.stdout)
            owner=build+'/'+source.removesuffix('.c')+'.o'
            pattern=(r'\.text\.'+re.escape(symbol)+r'\s+0x0*'+(entry[0] if len(entry)==1 else 'NO_OWNER')+
                r'\s+0x[\da-fA-F]+\s+'+re.escape(owner)+r'(?:\s|$)')
            if len(entry)!=1 or re.search(pattern,text) is None:
                raise ValueError('Native timer linked strong owner differs: '+symbol)
    print('PASS actual linked strong HAL_InitTick, TIM1 IRQ and period callback object owners')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['architecture','artifact','host'],default='architecture',nargs='?')
    parser.add_argument('--prefix',default='arm-none-eabi-')
    parser.add_argument('--host-cc',default='gcc')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if args.mode=='architecture':Architecture_Check(root)
    elif args.mode=='artifact':ProbeArtifact_Check(root,args.prefix)
    else:raise SystemExit('NOT PROVEN: timer probe has no Ground host program; run its dedicated actual-owner/counter fault tests')
