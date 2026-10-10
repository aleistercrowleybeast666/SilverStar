from pathlib import Path

task = Path(__file__).resolve().parent
root = Path(r'D:\python_software\SilverStar\.work\ccdi')
app = root / 'apps/SCG/src/silverstar_fccg/app'
(app / 'usb_ground.py').write_text((task / 'usb_ground.py.stage').read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
(root / 'apps/SCG/src/silverstar_fccg/hardware/usb_profiles/.gitattributes').write_text('*.json -text\n', encoding='utf-8')
service = app / 'service.py'
text = service.read_text(encoding='utf-8')
needle = '    def HardwareProviderForMcu_Get(self, mcu_id: str) -> str:\n'
assert needle in text
methods = '''    def UsbGroundProject_Import(self, input_path: Path, model: ProjectModel, **options):
        """Bind only the exact first-batch F103/C071 target; no GUI or release."""
        from silverstar_fccg.app.usb_ground import UsbGroundProject_Import
        return UsbGroundProject_Import(self.hardware_importer, self.catalog, input_path, model, **options)

    def UsbGroundCandidate_Plan(self, model: ProjectModel, **options):
        """Recheck backend facts and source identity; C071 reports its block."""
        from silverstar_fccg.app.usb_ground import UsbGroundCandidate_Plan
        return UsbGroundCandidate_Plan(self.hardware_importer, self.catalog, model, **options)

    def UsbGroundCandidate_Export(self, model: ProjectModel, output: Path, **options):
        from silverstar_fccg.app.usb_ground import UsbGroundCandidate_Export
        return UsbGroundCandidate_Export(self.hardware_importer, self.catalog, model, output, **options)

    def UsbGroundCandidate_Build(self, model: ProjectModel, project_root: Path, output: Path, **options):
        from silverstar_fccg.app.usb_ground import UsbGroundCandidate_Build
        return UsbGroundCandidate_Build(self.hardware_importer, self.catalog, model, project_root, output, **options)

'''
text = text.replace(needle, methods + needle)
service.write_text(text, encoding='utf-8', newline='\n')
renderer = root / 'apps/SCG/src/silverstar_fccg/generator/multi_target.py'
text = renderer.read_text(encoding='utf-8')
needle = '    if "native_complete_classic_cdc" in model.ground_target.hardware.inventory:\n'
assert text.count(needle) == 1
text = text.replace(needle, '    if any(key in model.ground_target.hardware.inventory for key in\n            ("native_complete_classic_cdc", "native_ground_backend", "usb_ground_c071_native")):\n')
renderer.write_text(text, encoding='utf-8', newline='\n')
text = service.read_text(encoding='utf-8')
needle = '        if "native_complete_classic_cdc" in inventory or "native_ground_backend" in inventory:\n'
assert text.count(needle) == 1
text = text.replace(needle, '        if any(key in inventory for key in ("native_complete_classic_cdc", "native_ground_backend", "usb_ground_c071_native")):\n')
service.write_text(text, encoding='utf-8', newline='\n')
print('Installed first-batch binding/dispatch; firmware payloads and GUI unchanged')
