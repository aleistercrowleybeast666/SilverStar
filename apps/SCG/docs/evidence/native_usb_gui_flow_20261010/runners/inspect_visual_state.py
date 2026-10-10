from pathlib import Path
p=Path(__file__).with_name('recapture_gui_visual_compare.py')
s=p.read_text(encoding='utf8')
anchor="s=s.replace(\" windows.append(window)\\n window.hide();app.processEvents()\", \" window.hide();app.processEvents()\")"
assert anchor in s
s=s.replace(anchor,anchor+"\ns=s.replace(\"  records.append({\",\"  records.append({'ground_generate_enabled':window.ground_target_page.generate_button.isEnabled(),'ground_generate_height':window.ground_target_page.generate_button.height(),'ground_generate_font':window.ground_target_page.generate_button.font().toString(),\")\ns=s.replace(\"'renders':records\",\"'renders':records,'ground_inventory_keys':list(models[0].ground_target.hardware.inventory)\")")
exec(compile(s,'visual_state_inspection','exec'),{'__file__':str(p)})
