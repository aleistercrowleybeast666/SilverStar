"""Fetch pinned official ST sources only; never execute their build files."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, urllib.request
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()
ROOT = args.output.resolve()
if ROOT.exists() and any(ROOT.iterdir()): raise ValueError('official snapshot output must be empty')
ROOT.mkdir(parents=True,exist_ok=True)
def request(url):
    with urllib.request.urlopen(url, timeout=60) as stream: return stream.read()
def tree(repo, revision):
    return json.loads(request('https://api.github.com/repos/STMicroelectronics/'+repo+'/git/trees/'+revision+'?recursive=1'))
app = tree('stm32c0-classic-coremw-apps', '334655ed5eb719db18fa5990a5044332eeca59dc')
pins = {entry['path']: entry['sha'] for entry in app['tree'] if entry['type']=='commit'}
specs = [('stm32c0-classic-coremw-apps', app['sha'], '', app,
          lambda p: p.startswith(('Drivers/CMSIS/Include/', 'Projects/NUCLEO-C071RB/Applications/USB_Device/CDC_Standalone/')) or p in ('.gitmodules','README.md','LICENSE.md','Release_Notes.html')),
         ('cmsis-device-c0', pins['Drivers/CMSIS/Device/ST/STM32C0xx'], 'Drivers/CMSIS/Device/ST/STM32C0xx/', None, lambda p: p.startswith(('Include/', 'Source/Templates/')) or p in ('README.md','LICENSE.md','Release_Notes.html')),
         ('stm32c0xx-hal-driver', pins['Drivers/STM32C0xx_HAL_Driver'], 'Drivers/STM32C0xx_HAL_Driver/', None, lambda p: p.startswith(('Inc/', 'Src/')) or p in ('README.md','LICENSE.md','Release_Notes.html')),
         ('stm32-mw-usb-device', pins['Middlewares/ST/STM32_USB_Device_Library'], 'Middlewares/ST/STM32_USB_Device_Library/', None, lambda p: p.startswith(('Core/Inc/', 'Core/Src/', 'Class/CDC/')) or p in ('README.md','LICENSE.md','Release_Notes.html'))]
tasks, manifests = [], []
for repo, revision, prefix, data, selected in specs:
    data = data or tree(repo, revision)
    manifests.append({'repo':'https://github.com/STMicroelectronics/'+repo, 'commit':revision, 'prefix':prefix})
    for entry in data['tree']:
        if entry['type']=='blob' and selected(entry['path']): tasks.append((repo, revision, prefix, entry))
def fetch(item):
    repo, revision, prefix, entry = item
    path = ROOT / (prefix+entry['path'])
    body = request('https://raw.githubusercontent.com/STMicroelectronics/'+repo+'/'+revision+'/'+entry['path'])
    git_sha = hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
    if git_sha != entry['sha']: raise ValueError('official Git blob hash mismatch: '+entry['path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {'path':path.relative_to(ROOT).as_posix(), 'git_blob_sha1':git_sha, 'sha256':hashlib.sha256(body).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    files = list(pool.map(fetch,tasks))
(ROOT/'source-manifest.json').write_text(json.dumps({'sources':manifests,'files':files},indent=2),encoding='utf8')
print('verified official files',len(files),'bytes',sum((ROOT/file['path']).stat().st_size for file in files))
