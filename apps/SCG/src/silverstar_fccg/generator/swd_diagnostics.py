"""Diagnostic data and an artifact receipt; binding stays in the SCG host."""
import json
from silverstar_diagnostics.contract import Schema_Create
from silverstar_diagnostics.targets import Target_Get
from silverstar_diagnostics.contract import DiagnosticError


def SwdDiagnostics_Render(model, catalog, makefile=None, *, role='flight'):
    part = model.hardware.mcu
    if not part:
        metadata = catalog.Component_Get(model.mcu).metadata
        part = metadata.get('part', metadata.get('mcu', 'unknown'))
    try: part = Target_Get(part).name
    except DiagnosticError: pass  # Schema remains explicit; unsupported target cannot bind.
    from silverstar_diagnostics.project_descriptor import ProjectDescriptor_Create, NAMES
    name=NAMES[role]
    declarations={}
    if role=='flight':
        selection=getattr(model,'protocols',{}).get('maintenance')
        declarations=dict(project_file='SilverStar.ssproject',maintenance=(dict(
            component=selection.component,package_version=selection.version,profile=selection.profile)
            if selection is not None else None))
        # Catalog-free diagnostic metadata has no resolved UART authority.
        # Keep its protocol declaration without inventing a resource baud.
        if selection is not None and catalog is not None:
            from silverstar_fccg.generator.maintenance_uart import MaintenanceUart_Declaration
            uart = MaintenanceUart_Declaration(model, catalog)
            if uart is not None:
                declarations['maintenance']['uart'] = uart
    files={name:json.dumps(ProjectDescriptor_Create(model.identity.name,part or 'unknown',role,**declarations),ensure_ascii=False,indent=2)}
    legacy=f'{model.identity.name}.ssdiag'
    if role=='flight' and legacy!=name:
        files[legacy]=json.dumps(Schema_Create(part or 'unknown'),ensure_ascii=False,indent=2)
    if makefile is not None:
        text=makefile.decode('utf-8') if isinstance(makefile,bytes) else makefile
        elf='$(BUILD_ROOT)/$(TARGET).elf' if role=='flight' else '$(BUILD_DIR)/ground.elf'
        # A successful all recipe reports its expanded output, including an
        # incremental build. It executes no metadata tools or source generator.
        text+=('\n# SCG host artifact receipt; no diagnostic writer runs in this build.\n'
               'ifneq ($(ANALYZE),1)\nall:\n'
               f'\t@echo "FCCG_BUILD_ARTIFACT|ELF|{elf}"\nendif\n')
        files['Makefile']=text
    return {n:v if isinstance(v,bytes) else v.encode('utf-8') for n,v in files.items()}
