from pathlib import Path
import subprocess,json
root=Path('D:/python_software/SilverStar/.work/ccdi')
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')=='05e20169240ec812c988af1017cffc495319ec3c'
assert git('branch','--show-current')=='feature/scg-classic-cdc-contract-20261009'
status=subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True)
paths=[line[3:] for line in status.splitlines()]
assert len(paths)==19 and all(p.startswith(('apps/SCG/src/','apps/SCG/tests/','apps/SCG/tools/','apps/SCG/plugins/')) for p in paths)
subprocess.run(['git','-C',str(root),'diff','--check'],check=True)
subprocess.run(['git','-C',str(root),'add','--',*paths],check=True)
subprocess.run(['git','-C',str(root),'commit','-m','SCG: integrate private native F407 Ground with TIM1 lifecycle'],check=True)
result={'code_commit':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),'paths':paths,
    'tested_snapshot':'Fresh 14e compiled dirty snapshot based on 05e2016; exact source bytes audited before evidence packaging',
    'daily_head':git('-C','D:/python_software/SilverStar','rev-parse','HEAD')}
Path(__file__).with_name('code-checkpoint.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
