"""Compare actual widget-construction and style code to accepted baseline."""
from pathlib import Path
import ast,hashlib,json,subprocess
repo=Path(r'D:\python_software\SilverStar\.work\ccdi');task=Path(__file__).parent
baseline='c55bdc3a16514f62c9a92b6a7582a7bbcdf132a3'
ui=repo/'apps/SCG/src/silverstar_fccg/ui'
files=subprocess.check_output(['git','-C',str(repo),'ls-files','apps/SCG/src/silverstar_fccg/ui'],text=True).splitlines()
changed=[];unaltered=[]
permitted={
 'main_window.py':{'_Project_Display','_TargetPages_Refresh','_GroundCubeMxImport_Request','_GroundCubeMxImport_Complete',
 '_GenerateOrApply_Request','_Project_Open','_Targets_Generate','_TargetQualityResults_Refresh','_QualityChecks_Request',
 '_QualityChecks_Complete','_TargetAction_Request','_UsbGroundOperation_Request','_UsbGroundTargetAction_Request'},
 'pages/build.py':{'Targets_Set','_TargetActions_Update'}}
for relative in files:
 old=subprocess.check_output(['git','-C',str(repo),'show',baseline+':'+relative])
 new=(repo/relative).read_bytes()
 if old.replace(b'\r\n',b'\n')==new.replace(b'\r\n',b'\n'):
  unaltered.append({'path':relative,'git_sha256':hashlib.sha256(old).hexdigest()});continue
 name=(repo/relative).relative_to(ui).as_posix();assert name in permitted,name
 def methods(body):
  node=ast.parse(body.decode('utf-8-sig'))
  return {n.name:ast.dump(n,include_attributes=False) for c in node.body if isinstance(c,ast.ClassDef)
    for n in c.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 a,b=methods(old),methods(new)
 touched=sorted(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
 assert set(touched)<=permitted[name],(name,touched)
 # Every widget/style/layout constructor and initialization function remains
 # identical, including page constructors and all stylesheet/theme files.
 assert a['__init__']==b['__init__'],name
 changed.append({'path':relative,'baseline_git_sha256':hashlib.sha256(old).hexdigest(),
  'current_working_sha256':hashlib.sha256(new).hexdigest(),'changed_logic_methods':touched,'widget_constructor_ast_identical':True})
record={'baseline':baseline,'scope':'Source and AST visual-boundary check, not a screenshot or whole-product visual PASS',
 'changed_logic_files':changed,'unchanged_ui_files':unaltered,'result':'Widget constructors, layout/styles/theme sources unchanged; only listed handlers/results/availability logic differ'}
(task/'usb-gui-visual-boundary.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print('Visual source boundary:',len(changed),'logic files;',len(unaltered),'other UI files unchanged')
