from pathlib import Path
import shutil
repo=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
source=repo/'docs/architecture/gui_field_blockers_20261002/reproduction'
out=repo/'docs/architecture/field_gui_integration_20261002/reproduction'
out.mkdir(parents=True,exist_ok=True)
for filename in ('capture_gui.py','capture_parent_comparison.py','capture_import_save.py'):
    content=(source/filename).read_text(encoding='utf-8').replace('GuiFieldBlockers_20261002','FieldGuiIntegration_20261002')
    content=content.replace("root/'apps/FCCG/.work/field_tests_r4'", "root/'apps/FCCG/.work/qall'")
    (out/filename).write_text(content,encoding='utf-8')
for filename in ('integration_verify.py','integration_entry_capture.py'):
    shutil.copyfile(Path(__file__).parent/filename,out/filename)
(out/'final_capture').mkdir(exist_ok=True)
print(out)
