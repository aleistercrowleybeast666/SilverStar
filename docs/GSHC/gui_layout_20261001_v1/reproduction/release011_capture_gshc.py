import os, pathlib, subprocess, sys
root=pathlib.Path(__file__).resolve().parents[1]
for language in ('zh_CN','en_US'):
    for size in ('1280x720','1536x816'):
        subprocess.run([sys.executable,str(root/'.work/gshc_layout_capture.py'),'delivered',size,language],check=True)
subprocess.run([sys.executable,str(root/'.work/gshc_layout_capture.py'),'historical','1536x816','zh_CN'],check=True)
env=os.environ.copy()
env['QT_SCALE_FACTOR']='1.2'
subprocess.run([sys.executable,str(root/'.work/gshc_layout_capture.py'),'delivered','1280x720','zh_CN'],env=env,check=True)
