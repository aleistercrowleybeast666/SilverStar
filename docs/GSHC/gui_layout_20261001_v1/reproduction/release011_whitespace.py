import json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
evidence=root/'docs/GSHC/gui_layout_20261001_v1'
records={}
for name,args in (('git_whitespace_all',['git','diff','--cached','--check']),
    ('git_whitespace_source',['git','diff','--cached','--check','--','.',':(exclude)docs/GSHC/gui_layout_20261001_v1/*.log'])):
    result=subprocess.run(args,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (evidence/(name+'.log')).write_bytes(result.stdout)
    records[name]={'command':args,'exit_code':result.returncode}
    if name.endswith('source'):
        assert result.returncode==0,result.stdout
(evidence/'git_whitespace.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print(json.dumps(records))
