from pathlib import Path
import ast,hashlib,json,subprocess
repo=Path(r'D:\python_software\SilverStar\.work\ccdi');task=Path(__file__).parent
baseline='bf22bdcd56e76687e8be40d5f221cb3c29668ec1'
allowed={'__init__','_Project_Display','_GroundCubeMxImport_Request','_TargetQualityResults_Refresh',
         '_UsbGroundRequest_Current','_UsbGroundRefresh_Invalidate','_UsbGroundRefresh_Request','_UsbGroundRefresh_Start',
         '_QualityChecks_Request','_UsbGroundOperation_Request','_UsbGroundTargetAction_Request','_Task_Finish','_Task_Cancel','closeEvent'}
init_added={
 'self._usb_refresh_epoch = 0','self._usb_refresh_pending = None','self._usb_refresh_worker = None',
 'self._usb_refresh_timer = QTimer(self)','self._usb_refresh_timer.setSingleShot(True)',
 'self._usb_refresh_timer.timeout.connect(self._UsbGroundRefresh_Start)'}
unchanged=[];changed=[]
for relative in subprocess.check_output(['git','-C',str(repo),'ls-files','apps/SCG/src/silverstar_fccg/ui'],text=True).splitlines():
    old=subprocess.check_output(['git','-C',str(repo),'show',baseline+':'+relative]);new=(repo/relative).read_bytes()
    if old.replace(b'\r\n',b'\n')==new.replace(b'\r\n',b'\n'):
        unchanged.append(relative);continue
    assert relative.endswith('/ui/main_window.py'),relative
    def methods(body):
        n=ast.parse(body.decode('utf-8-sig'))
        return {f.name:f for c in n.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef)}
    a,b=methods(old),methods(new)
    touched=sorted(k for k in a.keys()|b.keys() if (ast.dump(a[k]) if k in a else '')!=(ast.dump(b[k]) if k in b else ''))
    assert set(touched)<=allowed,touched
    constructor=b['__init__'];extra=[n for n in constructor.body if ast.unparse(n) in init_added]
    assert {ast.unparse(n) for n in extra}==init_added
    constructor.body=[n for n in constructor.body if ast.unparse(n) not in init_added]
    assert ast.dump(constructor,include_attributes=False)==ast.dump(a['__init__'],include_attributes=False)
    changed.append({'path':relative,'changed_methods':touched,'baseline_sha256':hashlib.sha256(old).hexdigest(),
                    'current_sha256':hashlib.sha256(new).hexdigest(),
                    'constructor_layout_widgets_styles_identical_after_only_owned_timer_fields_removed':True})
record={'baseline':baseline,'scope':'Widget/layout/style source+AST only; owned Qt timer/worker state is new backend lifecycle logic',
        'changed':changed,'unchanged_ui_files':unchanged,'owned_timer_additions':sorted(init_added)}
(task/'usb-async-visual-boundary.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps({'changed_ui_files':len(changed),'other_ui_files_unchanged':len(unchanged),'constructor_visual_ast_verified':True}))
