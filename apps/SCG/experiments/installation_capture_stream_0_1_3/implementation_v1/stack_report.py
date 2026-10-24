"""Isolated ELF call-chain report; never a task/MSP/ISR or WCET proof.

Uses the same conservative constant-SP accounting as the owning checker:
Tools/check_task_stacks.py. Tail branches are conservatively nested. Unresolved
indirect calls, cycles, dynamic frames or SP writes remain NOT PROVEN.
"""
import re


def registers(args,width):
    total=0
    for item in args.strip('{}').split(','):
        item=item.strip()
        if '-' in item:
            first,last=item.split('-');total+=int(re.search(r'\d+',last)[0])-int(re.search(r'\d+',first)[0])+1
        elif item:total+=1
    return total*width


def Report_Build(directory,disassembly):
    frames={};unknown=set();instructions={};library={}
    for path in directory.rglob('*.su'):
        for line in path.read_text(encoding='utf-8').splitlines():
            location,count,kind=line.split('\t');name=location.rsplit(':',1)[-1]
            frames[name]=max(frames.get(name,0),int(count))
            if kind not in ('static','dynamic,bounded'):unknown.add(name)
    name=None
    for line in disassembly.splitlines():
        header=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
        if header:name=header[1];instructions[name]=[]
        else:
            row=re.match(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{4,8}\s+)+(\S+)\s*(.*)',line)
            if row and name is not None:instructions[name].append((row[1],row[2]))
    edges={name:set() for name in instructions};indirect=set()
    for name,rows in instructions.items():
        frame=0
        for op,args in rows:
            target=re.search(r'<([^>+]+)(?:\+[^>]+)?>',args)
            if (op.startswith('b') or op in ('cbz','cbnz')) and target and target[1] in instructions and (target[1]!=name or op in ('bl','bl.w','blx')):
                edges[name].add(target[1])
            if (op=='blx' and '<' not in args) or (op.startswith('bx') and args.strip()!='lr'):indirect.add(name)
            if name in frames:continue
            if op.startswith(('push','stmdb')) and '{' in args:frame+=registers(args[args.index('{'):],4)
            elif op.startswith('vpush'):frame+=registers(args,8 if 'd' in args else 4)
            elif op.startswith('sub') and re.match(r'sp,\s*(?:sp,\s*)?#',args):frame+=int(re.search(r'#(0x[0-9a-f]+|\d+)',args)[1],0)
            elif re.search(r'\[sp,\s*#-(0x[0-9a-f]+|\d+)\]!',args):frame+=int(re.search(r'#-(0x[0-9a-f]+|\d+)',args)[1],0)
            elif re.search(r'\[sp[^\]]*\]!',args) or re.match(r'sp,',args) and op.startswith(('sub','mov','bic')):unknown.add(name)
        if name not in frames:frames[name]=frame;library[name]=frame
    def chain(name,active=()):
        if name in active:raise ValueError('recursion/cycle: '+' -> '.join((*active,name)))
        if name in unknown or name in indirect:raise ValueError('unresolved path: '+name)
        children=[chain(child,(*active,name)) for child in edges[name]]
        deeper=max(children,key=lambda value:value[0]) if children else (0,[])
        return frames[name]+deeper[0],[{'function':name,'frame':frames[name]},*deeper[1]]
    roots={}
    for name in sorted(instructions):
        if name.startswith(('InstallationCapture_','SystemInstallationCapture_')):
            try:
                count,path=chain(name);roots[name]={'bytes':count,'chain':path,'result':'KNOWN_STATIC_CHAIN'}
            except ValueError as exc:roots[name]={'bytes':None,'reason':str(exc),'result':'NOT PROVEN'}
    guard=[name for name in instructions if name.startswith('Capture_Enter')]
    return {'scope':'isolated module/library chains only; no caller task/context/MSP/ISR/hardware margin or WCET',
        'roots':roots,'frames':frames,'library_frames':library,'indirect':sorted(indirect),'unbounded':sorted(unknown),
        'edges':{name:sorted(children) for name,children in edges.items()},
        'guard_instructions':{name:instructions[name] for name in guard},
        'critical_contract_review':'NOT PROVEN','whole_program_stack_acceptance':'NOT PROVEN','wcet':'NOT PROVEN'}
