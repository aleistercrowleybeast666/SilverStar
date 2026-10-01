import subprocess, sys, pathlib, json, time, hashlib, os, datetime
root = pathlib.Path(__file__).resolve().parents[1]
evidence = root / 'docs/GSHC/gui_layout_20261001_v1'
evidence.mkdir(parents=True, exist_ok=True)
name, cwd, *cmd = sys.argv[1:]
for argument in cmd:
    if argument.startswith('--basetemp='):
        location = pathlib.Path(argument.partition('=')[2])
        if not location.is_absolute():
            location = root / cwd / location
        location.parent.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env['PYTHONPATH'] = os.pathsep.join([str(root/'apps/FCCG/src'), str(root/'apps/FCCG'), str(root/'apps/FCCG/tools')])
env['PYTHONDONTWRITEBYTECODE'] = '1'
env['QT_QPA_PLATFORM'] = 'windows'
env['PATH'] = 'D:/msys64/ucrt64/bin' + os.pathsep + env['PATH']
env['SILVERSTAR_GENERATED_DECODER_EXISTING'] = str(root/'.work/SCG_011_KF6_e02cca1_v1')
# Keep a run-specific auditable source snapshot before launching the command.
(evidence/(name+'.source.diff')).write_bytes(subprocess.check_output(['git','diff','--binary','HEAD'],cwd=root))
started = time.perf_counter()
with (evidence/(name+'.log')).open('wb') as log:
    result = subprocess.run(cmd, cwd=root/cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
record = dict(command=cmd, cwd=str(root/cwd), exit_code=result.returncode,
              utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), seconds=time.perf_counter()-started,
              head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=root).decode().strip(),
              log_sha256=hashlib.sha256((evidence/(name+'.log')).read_bytes()).hexdigest(),
               environment=dict(QT_QPA_PLATFORM='windows', PYTHONPATH=env['PYTHONPATH'],
                   SILVERSTAR_GENERATED_DECODER_EXISTING=env['SILVERSTAR_GENERATED_DECODER_EXISTING']))
(evidence/(name+'.json')).write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps(record))
print((evidence/(name+'.log')).read_text(encoding='utf-8',errors='replace')[-5000:].encode('ascii','backslashreplace').decode())
sys.exit(result.returncode)
