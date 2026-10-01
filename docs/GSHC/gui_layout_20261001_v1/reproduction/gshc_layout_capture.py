import hashlib, importlib.util, json, os, pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[1]
work = root/'.work/gshc_layout_20261001'
work.mkdir(exist_ok=True)
evidence = root/'docs/GSHC/gui_layout_20261001_v1'
evidence.mkdir(exist_ok=True)
sys.path[:0] = [str(root/'apps/GSHC'), str(root/'apps/GSHC/tests')]
os.environ['QT_QPA_PLATFORM'] = 'windows'
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtWidgets import QApplication, QGroupBox
from services.i18n import I18n
from services.state_model import EventHistory
from test_ui_workflow import ready_state
from ui.main_window import MainWindow

variant, size, language = sys.argv[1:]
width,height=map(int,size.split('x'))
if variant == 'historical':
    raw=subprocess.check_output(['git','-c','safe.directory=D:/python_software/SilverStar_GSHC','-C','D:/python_software/SilverStar_GSHC','show','8be9fd6^:ui/main_window.py'])
    path=work/'historical_main_window.py'
    path.write_bytes(raw)
    spec=importlib.util.spec_from_file_location('ui.historical_main_window',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    MainWindow=module.MainWindow
else:
    raw=(root/'apps/GSHC/ui/main_window.py').read_bytes()
app=QApplication([])
settings=QSettings(str(work/(variant+'_'+size+'_'+language+'_'+os.environ.get('QT_SCALE_FACTOR','1')+'.ini')),QSettings.IniFormat)
settings.clear()
i18n=I18n(settings)
i18n.set_language(language)
window=MainWindow(i18n)
window.render_timer.stop()
state=ready_state()
state.sensor.accel_mps2=(0.125,-0.375,9.807)
state.sensor.gyro_radps=(0.012,-0.025,0.001)
state.sensor.quat=(1.0,0.0,0.0,0.0)
state.sensor.quat_valid=True
state.sensor.euler_rpy=(0.01,-0.02,1.57)
state.sensor.velocity_mps=(12.345,-6.789,20.012)
state.sensor.position_m=(123.456,-234.567,1200.012)
state.sensor.revision=1
window.bind_runtime_model(state,EventHistory())
window.resize(width,height)
window.show()
app.processEvents()
window.resize(width,height)
record=dict(source_sha256=hashlib.sha256(raw).hexdigest(), requested_size=[width,height],
    qt_scale=os.environ.get('QT_SCALE_FACTOR','1'),device_pixel_ratio=window.devicePixelRatioF(),pages={})
for name in ('preflight','flight'):
    page=getattr(window,name+'_page')
    window.pages.setCurrentWidget(page)
    for _ in range(3):app.processEvents()
    groups=[]
    for box in page.findChildren(QGroupBox):
        p=box.mapTo(window,QPoint(0,0))
        groups.append(dict(title=box.title(),geometry=[p.x(),p.y(),box.width(),box.height()],visible=box.isVisible()))
    labels={}
    for attr in ('lbl_pf_system_ready','lbl_pf_selftest','lbl_cal_ready','lbl_align_ready','lbl_pf_accel','lbl_pf_gyro','lbl_pf_gnss_usable','btn_start','event_list','lbl_flight_lifecycle','lbl_packet_loss','lbl_flight_accel','lbl_flight_vel','lbl_flight_pos','lbl_mission_parachute'):
        widget=getattr(window,attr)
        if page.isAncestorOf(widget):
            p=widget.mapTo(window,QPoint(0,0))
            labels[attr]=dict(geometry=[p.x(),p.y(),widget.width(),widget.height()],visible=widget.isVisible(),text=widget.text() if hasattr(widget,'text') else '')
    record['pages'][name]=dict(groups=groups,labels=labels,window_size=[window.width(),window.height()],
        scrollbar_maximum=page.verticalScrollBar().maximum() if hasattr(page,'verticalScrollBar') else None)
    filename=f'{variant}_{language}_{size}_scale{os.environ.get("QT_SCALE_FACTOR","1")}_{name}.png'
    assert window.grab().save(str(evidence/filename))
(evidence/(f'{variant}_{language}_{size}_scale{os.environ.get("QT_SCALE_FACTOR","1")}.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
window.close()
app.processEvents()
print(json.dumps(record,ensure_ascii=True))
