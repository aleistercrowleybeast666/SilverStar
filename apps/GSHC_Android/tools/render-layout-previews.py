"""Local Edge HTML design evidence only; no Android, SDK, USB, or network validation."""
from pathlib import Path
import html
import json
import re
import subprocess

root = Path(__file__).resolve().parents[1]
edge = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
if not edge.is_file():
    raise SystemExit('Local Edge unavailable; preview rendering not performed')
output_dir = root / 'evidence'
output_dir.mkdir(exist_ok=True)
pages = ['preflight', 'flight', 'postprocessing', 'maintenance']
configurations = [('phone',360,800,1),('tablet',1200,800,1),('split',480,800,1),('phone-font200',360,800,2)]
# Four extra short-window checks supplement the 16 requested combinations.
configurations.append(('short-landscape',640,360,1))
results = []
for configuration,width,height,scale in configurations:
    for page,page_name in enumerate(pages):
        name = f'{configuration}-{page_name}-layout-preview'
        url = (root/'docs/layout-preview.html').as_uri()+f'?capture=1&page={page}&width={width}&height={height}&scale={scale}'
        keep_screenshot = configuration=='phone' or (configuration=='tablet' and page==1) or (configuration=='phone-font200' and page==3)
        screenshot = output_dir/(name+'.png')
        args = [str(edge),'--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',
                f'--user-data-dir={root/"build/preview-browser"}',f'--window-size={width},{height}','--hide-scrollbars',
                '--force-device-scale-factor=1','--virtual-time-budget=1200','--dump-dom']
        if keep_screenshot:
            args.append(f'--screenshot={screenshot}')
        args.append(url)
        process = subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        output = process.stdout.decode('utf-8',errors='replace')
        match = re.search(r'<pre id="layout-check">(.*?)</pre>',output)
        if process.returncode or not match:
            raise SystemExit(f'Preview failed: {name}; exit {process.returncode}; {process.stderr.decode(errors="replace")[-600:]}')
        result = json.loads(html.unescape(match[1]))
        if result['overflow']:
            raise SystemExit(f'Horizontal overflow: {name}: {result["overflow"]}')
        if result['portCount']!=2 or result['portOrder']!=['ground','debug'] or result['duplicatePagePortControls']:
            raise SystemExit(f'Independent header port control failure: {name}')
        if page==3 and not result['downloadRequiresTarget']:
            raise SystemExit(f'Target selection gate missing: {name}')
        a,b=result['portRects']
        if (width>=600 and not(a['x']<b['x'] and a['y']==b['y'])) or (width<600 and not(a['y']<b['y'] and a['x']==b['x'])):
            raise SystemExit(f'Header port placement failure: {name}')
        if page==1 and (result['order']!=([0,3,1,4,2,5] if width<840 else [0,1,2,3,4,5]) or result['columns']!=(2 if width<840 else 3)):
            raise SystemExit(f'Curve order/columns failure: {name}')
        if not result['scrollReachable'] or result['mainAvailablePx']<min(220,height*.33):
            raise SystemExit(f'Main scroll area obscured by header/navigation: {name}: {result["mainAvailablePx"]}')
        results.append(dict(name=name,screenshot=screenshot.name if keep_screenshot else None,**result))
        print(f'PASS {name}: content {result["mainAvailablePx"]} px; ports {result["portLayout"]}',flush=True)
report={'scope':'HTML browser design preview ONLY; not Android APK/emulator/device screenshots',
        'requested_cases':16,'additional_short_window_cases':4,'retained_screenshots':6,
        'limitations':['CSS font scaling approximates 200% text; no Android fontScale execution.','Compact collapsible header is a proposed native adaptation, not evidence that MainActivity implements it.','Static synthetic values and curves; device and file actions are not executed.','Maintenance screenshots are scrolled to the TF target-selection card; others show initial viewport. DOM checks verify vertical scroll reachability.'],
        'cases':results}
(output_dir/'layout-preview-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PASS: {len(results)} HTML preview cases; six retained screenshots; four pages x four required configurations plus four short-landscape cases.')
