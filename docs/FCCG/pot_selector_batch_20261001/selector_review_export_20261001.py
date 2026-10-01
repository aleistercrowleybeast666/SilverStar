from pathlib import Path
import csv, datetime, hashlib, json, re, shlex, subprocess, zipfile
r=Path(__file__).resolve().parents[3]; evidence=r/'docs/FCCG/pot_selector_batch_20261001'; generated=r/'.work/SelectorSafety_70ce20d_20261001_v1/after/Flight_Controller'; output=r/'.work/PoT171_Review_20261001_v8'; assert not output.exists(); output.mkdir()
inventory=json.loads((evidence/'inventory.json').read_text()); counts=json.loads((evidence/'after_function_counts_full.json').read_text(encoding='utf-8-sig')); source_entries=[]; rows=[]; needed=set(); includes=re.compile(r'^\s*#\s*include\s*"([^"]+)"',re.M)
header_map={}
for p in generated.rglob('*.h'):
    if 'build' not in p.relative_to(generated).parts and 'Tests' not in p.relative_to(generated).parts:
        header_map.setdefault(p.name,[]).append(p)
for number,item in enumerate(inventory['remaining'],1):
    owner=r/item['repository_owner']; actual=generated/item['firmware_path']; assert owner.read_bytes()==actual.read_bytes(),owner
    matches=[x for x in counts if x['Name']==item['function'] and x['File'].replace('\\','/')==item['firmware_path']]; assert len(matches)==1
    info=matches[0]; assert info['StartLine']==item['line']; text=owner.read_text(encoding='utf-8'); masked=list(text); state='normal'; index=0
    while index<len(text):
        c=text[index]; nxt=text[index+1] if index+1<len(text) else ''
        if state=='normal':
            if c=='/' and nxt in ['/', '*']: state='line' if nxt=='/' else 'block'; masked[index]=' '; masked[index+1]=' '; index+=2; continue
            if c in ['\"', "'"]: state=c; masked[index]=' '
        elif state=='line':
            if c=='\n': state='normal'
            else: masked[index]=' '
        elif state=='block':
            if c=='*' and nxt=='/': masked[index]=' ';masked[index+1]=' ';index+=2;state='normal';continue
            if c!='\n':masked[index]=' '
        else:
            if c=='\\' and nxt: masked[index]=' '; masked[index+1]='\n' if nxt=='\n' else ' ';index+=2;continue
            if c==state:state='normal'
            if c!='\n':masked[index]=' '
        index+=1
    sanitized=''.join(masked)
    pattern=r'(?m)^[ \t]*(?:[A-Za-z_]\w*[ \t*\r\n]+)*'+re.escape(item['function'])+r'\s*\([^;{}]*\)\s*\{'
    definitions=[]
    for match in re.finditer(pattern,sanitized):
        if re.match(r'\s*(?:return|if|else|while|for)\b',match.group()): continue
        signature_open=sanitized.index('(',sanitized.index(item['function'],match.start(),match.end()),match.end());balance=1;cursor=signature_open+1
        while balance:
            if sanitized[cursor]=='(':balance+=1
            elif sanitized[cursor]==')':balance-=1
            cursor+=1
        if re.match(r'\s*\{',sanitized[cursor:]): definitions.append(match)
    assert len(definitions)==1,(item['function'],len(definitions))
    definition=definitions[0]; start=definition.start(); brace=sanitized.index('{',definition.start(),definition.end()); depth=1;end=brace+1
    while depth:
        assert end<len(text)
        if sanitized[end]=='{':depth+=1
        elif sanitized[end]=='}':depth-=1
        end+=1
    actual_line=text.count('\n',0,start)+1;actual_end_line=text.count('\n',0,end)+1;body=text[start:end]+'\n';assert item['function'] in body; assert item['function'] in body
    row={**item,'number':number,'end_line':actual_end_line,'actual_line':actual_line,'checker_end_line':info['EndLine'],'code_lines':info['CodeLines'],'source_sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),'function_body':body}
    rows.append(row); path=output/'functions'/('%03d_%s.c.txt'%(number,item['function'])); path.parent.mkdir(exist_ok=True); path.write_text(body,encoding='utf-8'); needed.add(actual)
# Ask the actual selected ARM compile configuration for its header closure.
# Inactive HAL/RTOS variants are unrelated to this build and are not bundled.
missing=set(); ambiguous=[]; dependency_commands=[]
compile_lines=(evidence/'after_flight_static.log').read_text(encoding='utf-8',errors='replace').splitlines()
for i,source in enumerate(sorted(needed)):
    relative=source.relative_to(generated).as_posix()
    command=next(shlex.split(line) for line in compile_lines if line.startswith('"D:/Arm GNU Toolchain/') and ' -c ' in line and (' '+relative+' -o ') in line)
    dep=output/('dependency_%02d.d'%i)
    args=[]; skip=False
    for index,arg in enumerate(command):
        if skip:skip=False;continue
        if arg in ['-o','-MF']:skip=True;continue
        if arg in ['-c','-MMD','-MP']:continue
        args.append(arg)
    args += ['-MM','-MF',str(dep),'-MT','review']
    result=subprocess.run(args,cwd=generated,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,(relative,result.stdout,result.stderr)
    dependencies=shlex.split(dep.read_text(encoding='utf-8').replace('\\\n',' ').split(':',1)[1])
    for name in dependencies:
        target=(generated/name).resolve()
        if target.is_relative_to(generated) and target.is_file() and target.suffix=='.h':needed.add(target)
    dependency_commands.append({'source':relative,'command':args,'exit_code':result.returncode,'dependency_sha256':hashlib.sha256(dep.read_bytes()).hexdigest()})
    dep.unlink()
for source in sorted(needed):
    relative=source.relative_to(generated); target=output/'firmware'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());source_entries.append({'package_path':str(target.relative_to(output)).replace('\\','/'),'generated_relative':relative.as_posix(),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
checker=generated/'Tools/check_power_of_ten.ps1';target=output/'checker/check_power_of_ten.ps1';target.parent.mkdir();target.write_bytes(checker.read_bytes())
# Build policy and source manifests are text necessary to interpret the checker's coverage.
for name in ['Makefile','Generated/project_sources.mk','Targets/SilverStar_F407/target.mk']:
    source=generated/name
    if source.exists(): target=output/'build_policy'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
(output/'functions.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
with (output/'index.csv').open('w',encoding='utf-8-sig',newline='') as f:
    keys=['number','firmware_path','repository_owner','function','line','actual_line','end_line','assertions','required','code_lines','source_sha256','status']; writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(); dirty=subprocess.check_output(['git','status','--porcelain'],cwd=r,text=True); diff=subprocess.check_output(['git','diff','HEAD','--binary'],cwd=r)
# The patch is restricted to the touched firmware source and AGENTS; no unneeded tests/logs or other docs are transferred.
limited_diff=subprocess.check_output(['git','diff','HEAD','--binary','--','AGENTS.md','apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_source_selector.c'],cwd=r)
(output/'source_snapshot.diff').write_bytes(limited_diff);(output/'AGENTS.md').write_bytes((r/'AGENTS.md').read_bytes())
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_commit':head,'dirty_status':dirty,'full_tracked_dirty_snapshot_sha256':hashlib.sha256(diff).hexdigest(),'included_dirty_snapshot_sha256':hashlib.sha256(limited_diff).hexdigest(),'strict_remaining':len(rows),'threshold':'functions >20 code lines need >=2 useful runtime assertions; strict N=2/M=20','scope':'17 corresponding complete first-party C files; actual selected-configuration required local headers, macros, unmodified checker and text build policy; no secret/user logs/binaries/full firmware','files':source_entries,'checker_sha256':hashlib.sha256(checker.read_bytes()).hexdigest(),'source_batch_evidence_sha256':hashlib.sha256((evidence/'result.json').read_bytes()).hexdigest(),'header_resolution':'Exact selected ARM -MM dependency closure, excluding compiler standard library and inactive target variants','dependency_commands':dependency_commands,'missing_headers':sorted(missing),'ambiguities':ambiguous,'semantic_review':'To be performed by parent; export provides function bodies without new semantic decisions','authorization':'User explicitly approved the limited source review ZIP transfer to their own ChatGPT Library on 2026-10-01'}
manifest['included_file_sha256']={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}; (output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
(output/'README.md').write_text('''# PoT 171 function review snapshot

Source commit and exact dirty snapshot hashes: manifest.json.
171 numbered findings: index.csv; complete function bodies: functions.json and functions/.
Complete corresponding C files and their required quoted local headers: firmware/.
The original checker and text source/build policy are included. The line column is the original checker diagnostic; actual_line/end_line identify raw source lines. Escaped newlines in C strings can make the original checker line mapping drift; bodies are independently brace-matched with comments/literals masked while preserving positions. Header includes with angle brackets are compiler standard-library interfaces and are not bundled. This is a limited review package, not a whole firmware project or a buildable replacement.
No logs, user recordings, secrets, firmware binaries, vendor C implementations or unrelated source files are included. No semantic judgments for the remaining findings have been added; the parent will review them. Strict N=2/M=20 remains authoritative; Flight still FAIL.
''',encoding='utf-8')
archive=output.with_suffix('.zip')
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(output.rglob('*')):
        if p.is_file(): z.write(p,p.relative_to(output).as_posix())
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
record={'path':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'findings':len(rows),'c_files':len({x['firmware_path'] for x in rows}),'headers':sum(p.suffix=='.h' for p in needed),'source_commit':head,'manifest_sha256':hashlib.sha256((output/'manifest.json').read_bytes()).hexdigest()};(evidence/'review_export.json').write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record))
