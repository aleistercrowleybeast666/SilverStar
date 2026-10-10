"""Private C071 ordinary architecture/Host/artifact checks; USB acceptance NOT PROVEN."""
from pathlib import Path
import argparse, hashlib, json, re
from ground_c071_contract import C071Architecture_Validate,C071EffectiveMacros_Validate

def Architecture_Check(root):
    graph=json.loads((root/'Generated/ground_source_graph.json').read_text())
    C071Architecture_Validate(root,graph)
    records=json.loads((root/'Generated/native_ground_contract.json').read_text())
    if graph.get('formal_release') is not False or graph.get('independent_usb_review') != 'NO_PASSED_OUTCOME':
        raise ValueError('Private C071 release/review boundary changed')
    make=(root/'Makefile').read_text().replace('\\\n',' ')
    for key,var in (('sources','C_SOURCES'),('asm_sources','ASM_SOURCES')):
        match=re.search(r'^'+var+r' := (.*)$',make,re.M)
        if match is None or match[1].split()!=graph[key] or len(set(graph[key]))!=len(graph[key]):
            raise ValueError('C071 Make/source graph differs')
    for path,digest in records['original_sha256'].items():
        if hashlib.sha256((root/'HardwareGenerated/STM32CubeMX'/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('C071 native byte identity differs')
    for path,digest in records['compiled_owned_sha256'].items():
        if path not in graph['sources'] or hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('C071 compiled owner changed: '+path)
    if graph['required_link_symbols']!=['_sbrk'] or '-Wl,-u,_sbrk' not in make or any(p.endswith('/sysmem.c') for p in graph['sources']):
        raise ValueError('C071 no-heap ownership differs')
    return graph

def Host_Check(root,compiler):
    from check_ground import Host_Check as NormalHost_Check
    directory=root/'build/c071-host-support';directory.mkdir(parents=True,exist_ok=True)
    stub=directory/'service.c'
    stub.write_text('#include "pc_c071_usb.h"\nvoid PcC071Usb_Service(void) {}\n')
    NormalHost_Check(root,compiler,extra_bridge_sources=(str(stub),),extra_includes=('Platform/STM32C0/Inc',))
    print('C071 endpoint service is mocked in these ordinary bridge/transport Host checks; lifecycle NOT PROVEN')

def Artifact_Check(root,prefix):
    from check_native_ground import Artifact_Check as SharedArtifact_Check
    SharedArtifact_Check(root,prefix,architecture_check=Architecture_Check)
    C071EffectiveMacros_Validate(root,Architecture_Check(root),prefix+'gcc')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('architecture','host','artifact'),default='architecture',nargs='?')
    parser.add_argument('--host-cc',default='gcc');parser.add_argument('--prefix',default='arm-none-eabi-')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if args.mode=='architecture':Architecture_Check(root)
    elif args.mode=='host':Host_Check(root,args.host_cc)
    else:Artifact_Check(root,args.prefix)
