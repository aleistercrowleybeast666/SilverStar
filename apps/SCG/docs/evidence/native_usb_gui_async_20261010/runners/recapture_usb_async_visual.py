from pathlib import Path
p=Path(__file__).with_name('capture_usb_async_visual.py')
s=p.read_text(encoding='utf8')
s=s.replace("out=task/'usb-async-visual';", "out=task/'usb-async-visual-settled';")
old=""" window._model=deepcopy(models[0]);window._Project_Refresh();window.resize(1280,820);window.show()
 for page,widget in [('ground',window.ground_target_page),('build',window.build_page)]:"""
new=""" window._model=deepcopy(models[0]);window._Project_Refresh();window.resize(1280,820)
 windows.append(window)
for label,window in zip(['baseline','current'],windows):
 window.show()
 for page,widget in [('ground',window.ground_target_page),('build',window.build_page)]:"""
assert old in s;s=s.replace(old,new)
s=s.replace('  for _ in range(3):app.processEvents();time.sleep(0.02)','  for _ in range(70):app.processEvents();time.sleep(0.01)')
s=s.replace(" windows.append(window)\n window.hide();app.processEvents()", " window.hide();app.processEvents()")
exec(compile(s,'settled_offscreen_render','exec'),{'__file__':str(p)})
