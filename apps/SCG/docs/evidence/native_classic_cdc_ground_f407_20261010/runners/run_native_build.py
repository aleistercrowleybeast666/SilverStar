from pathlib import Path
import os,sys,subprocess,json,datetime
root=Path('D:/python_software/SilverStar/.work/ccdi');out=Path(__file__).resolve().parent
family,label=sys.argv[1:3]
target=Path('C:/Users/chdxm/AppData/Local/Temp')/('ccdi-handoff-ground-'+family+'-'+label)
facts='f407-usb13.json' if family=='f407' else 'f103-usb.json'
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B','apps/SCG/tools/validation/native_classic_cdc_compile.py',
    '--input','C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation/cube-'+family+'-usb',
    '--device-facts','D:/python_software/SilverStar/.work/ccdi_facts/'+facts,'--output',str(target),
    '--spi','SPI1','--gpio','RADIO_NSS' if family=='f407' else 'SPI_RADIO_NSS','RADIO_RST','RADIO_BUSY','RADIO_DIO1',
    '--clock-hz','168000000' if family=='f407' else '72000000','--runtime-project',
    'C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject']
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='D:/python_software/SilverStar/.venv/Lib/site-packages')
record={'command':command,'cwd':str(root),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(out/(family+'-'+label+'-command.json')).write_text(json.dumps(record,indent=2))
with (out/(family+'-'+label+'.log')).open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
record['exit']=result.returncode;record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(out/(family+'-'+label+'-command.json')).write_text(json.dumps(record,indent=2))
(out/(family+'-'+label+'.exit')).write_text(str(result.returncode));print(family,label,result.returncode)
