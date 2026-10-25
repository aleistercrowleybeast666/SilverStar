"""Shared mission instances, explicit legacy adapters and reference-only intervals."""
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import runpy
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[5]
_API = runpy.run_path(str(_ROOT / 'tools/silverstar_mission_functions.py'))
Functions_Require = _API['Functions_Require']
FunctionCoverage_Get = _API['FunctionCoverage_Get']
BoundaryIndex_Get = _API['BoundaryIndex_Get']
FunctionsReferenceRunner = _API['FunctionsReferenceRunner']


@dataclass(frozen=True, slots=True)
class FunctionIssue:
    function_id: str
    code: str
    message: str
    level: str = 'error'
    stage_id: str = ''


def FunctionsCatalog_Get(catalog):
    contract = json.loads((_ROOT / 'contracts/mission_functions_v1.json').read_text(encoding='utf-8'))
    entries = []
    installed = {manifest.component_id for manifest in catalog.All_Get()}
    for adapter in contract['adapters']:
        if adapter['plugin_id'] not in installed: continue
        manifest = catalog.Component_Get(adapter['plugin_id'])
        if manifest.version != adapter['supported_version']: continue
        entries.append({**deepcopy(adapter), 'version': manifest.version,
            'name': {language: manifest.DisplayName_Get(language) for language in ('zh_CN','en_US')},
            'inputs': list(manifest.capabilities_required),
            'parameter_owner': manifest.component_id if manifest.algorithm_parameters else '',
            'measurement_any_of': list(manifest.metadata.get('measurement_any_of', ()))})
    return entries


def Function_Create(plugin_id, catalog, instance_id=None):
    declaration = next((entry for entry in FunctionsCatalog_Get(catalog) if entry['plugin_id'] == plugin_id), None)
    if declaration is None: raise ValueError('mission_functions_plugin_unsupported:' + plugin_id)
    return {'instance_id': instance_id or declaration['instance_id'], 'plugin_id': plugin_id,
        'category': declaration['category'], 'execution': declaration['executions'][0],
        'start': {'kind': declaration['start'], 'stage_id': ''},
        'stop': {'kind': declaration['stop'], 'stage_id': ''},
        'depends_on': [], 'input_bindings': {}, 'output': declaration['output']}


def Functions_Derive(model, catalog):
    if model.mission_functions is not None: return deepcopy(model.mission_functions)
    selected = set(model.ComponentIds_Get())
    functions = []
    for declaration in FunctionsCatalog_Get(catalog):
        if declaration['plugin_id'] not in selected: continue
        if declaration['instance_id'] == 'calibration' and not model.modes.get('calibration'): continue
        function = Function_Create(declaration['plugin_id'], catalog)
        functions.append(function)
    identities = {row['instance_id'] for row in functions}
    for function in functions:
        if function['instance_id'] == 'estimator' and 'ins' in identities: function['depends_on'] = ['ins']
    from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
    resolution = CapabilityResolution_Resolve(model, catalog)
    for function in functions:
        function['input_bindings'] = {route.requirement.capability: route.provider.instance_id
            for route in resolution.routes if route.requirement.consumer_component == function['plugin_id']}
    return {'schema_version': 1, 'functions': functions}


def Functions_Update(model, catalog, functions):
    result = deepcopy(model)
    result.mission_functions = Functions_Require(functions)
    return result


def FunctionsCanonical_Get(model, catalog):
    """Explicitly request the current authority's bindings, never overwrite a draft."""
    candidate = deepcopy(model)
    candidate.mission_functions = None
    return Functions_Derive(candidate,catalog)


def FunctionsStrategies_Synchronize(previous, candidate, catalog):
    """Reflect an explicit authority change without repairing user overrides."""
    if previous.mission_functions is None or candidate.mission_functions is None:
        return candidate
    before={row['instance_id']:row for row in FunctionsCanonical_Get(previous,catalog)['functions']}
    after={row['instance_id']:row for row in FunctionsCanonical_Get(candidate,catalog)['functions']}
    result=deepcopy(candidate)
    functions=result.mission_functions['functions']
    for identity in dict.fromkeys([*before,*after]):
        old,new=before.get(identity),after.get(identity)
        if (old or {}).get('plugin_id')==(new or {}).get('plugin_id'): continue
        existing=next((row for row in functions if row['instance_id']==identity),None)
        if existing is not None and old is not None and existing['plugin_id']!=old['plugin_id']:
            continue  # The caller already edited the instance; keep its explicit result.
        if new is None:
            if existing is not None: functions.remove(existing)
        elif existing is None:
            functions.append(deepcopy(new))
        else:
            replacement=deepcopy(new)
            replacement['start']=deepcopy(existing['start']);replacement['stop']=deepcopy(existing['stop'])
            for key in ('input_bindings','depends_on'):
                if old is None or existing[key]!=old[key]: replacement[key]=deepcopy(existing[key])
            functions[functions.index(existing)]=replacement
    result.mission_functions=Functions_Require(result.mission_functions)
    return result


def Functions_Issues(model, catalog):
    if model.mission_functions is None: return ()
    configuration = Functions_Require(model.mission_functions)
    declarations = {row['plugin_id']: row for row in FunctionsCatalog_Get(catalog)}
    rows = configuration['functions']; by_id = {row['instance_id']: row for row in rows}
    stage_ids = [stage['stage_id'] for stage in model.mission_process['stages']] if model.mission_process else []
    selected = set(model.ComponentIds_Get()); devices = {row.instance_id: row for row in model.device_instances}
    issues, plugins, outputs = [], set(), set()
    from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
    resolution = CapabilityResolution_Resolve(model, catalog)
    routes = resolution.routes
    def Add(function, code, message):
        issues.append(FunctionIssue(function['instance_id'], code, message))
    for function in rows:
        declaration = declarations.get(function['plugin_id'])
        if declaration is None:
            Add(function, 'FUNCTION_PLUGIN_UNSUPPORTED', 'Plugin has no declared mission adapter'); continue
        if function['plugin_id'] not in selected:
            Add(function, 'FUNCTION_PLUGIN_NOT_SELECTED', 'Plugin is not selected by the project authority')
        if declaration['instance_id'] == 'calibration' and not model.modes.get('calibration'):
            Add(function, 'FUNCTION_CALIBRATION_MODE_MISSING', 'Select an existing calibration mode; a card alone does not enable calibration')
        if function['plugin_id'] in plugins:
            Add(function, 'FUNCTION_SINGLETON', 'This plugin supports one runtime instance')
        plugins.add(function['plugin_id'])
        if function['output'] in outputs: Add(function, 'FUNCTION_OUTPUT_CONFLICT', 'Multiple functions own ' + function['output'])
        outputs.add(function['output'])
        if function['execution'] not in declaration['executions'] or function['category'] != declaration['category'] or function['output'] != declaration['output']:
            Add(function, 'FUNCTION_DECLARATION_MISMATCH', 'Execution, category or output disagrees with plugin adapter')
        start, stop = (BoundaryIndex_Get(function[key], stage_ids) for key in ('start','stop'))
        if start is None or stop is None:
            Add(function, 'FUNCTION_STAGE_MISSING', 'A referenced stage boundary is missing')
        elif start >= stop:
            Add(function, 'FUNCTION_INTERVAL_INVALID', 'Start must precede stop; the interval is [start, stop)')
        if function['start']['kind'] != declaration['start'] or function['stop']['kind'] != declaration['stop']:
            Add(function, 'FUNCTION_REFERENCE_ONLY', 'Custom interval has no firmware scheduling consumer; desktop reference only')
        for dependency in function['depends_on']:
            if dependency not in by_id:
                Add(function, 'FUNCTION_DEPENDENCY_MISSING', 'Missing dependency ' + dependency); continue
            upstream = by_id[dependency]
            upstream_start, upstream_stop = (BoundaryIndex_Get(upstream[key], stage_ids) for key in ('start','stop'))
            if None not in (start, stop, upstream_start, upstream_stop) and (upstream_start > start or upstream_stop < stop):
                Add(function, 'FUNCTION_INPUT_INTERVAL', 'Dependency does not cover this function interval: ' + dependency)
        expected_dependencies = ['ins'] if function['instance_id'] == 'estimator' and 'ins' in by_id else []
        if function['depends_on'] != expected_dependencies:
            Add(function, 'FUNCTION_DEPENDENCY_REFERENCE_ONLY', 'Custom dependency scheduling has no firmware consumer')
        expected_inputs = {route.requirement.capability: route.provider.instance_id for route in routes
                           if route.requirement.consumer_component == function['plugin_id']}
        if function['input_bindings'] != expected_inputs:
            Add(function, 'FUNCTION_INPUT_REFERENCE_ONLY', 'Input bindings differ from the canonical project capability routes')
        for capability, identity in function['input_bindings'].items():
            device = devices.get(identity)
            resolved = any(route.provider.instance_id == identity and route.requirement.capability == capability for route in routes)
            if device is None or (not resolved and capability not in catalog.Component_Get(device.plugin).provides):
                Add(function, 'FUNCTION_INPUT_MISSING', 'Input binding is unavailable: ' + capability + ':' + identity)
    for declaration in declarations.values():
        if declaration['plugin_id'] in selected and declaration['plugin_id'] not in plugins:
            if declaration['instance_id'] == 'calibration' and not model.modes.get('calibration'): continue
            issues.append(FunctionIssue(declaration['instance_id'], 'FUNCTION_SELECTED_UNBOUND',
                'Selected plugin is missing its shared function instance: ' + declaration['plugin_id']))
    for slot in ('ins','estimator','alignment'):
        plugin=model.strategies.get(slot)
        if plugin is not None and plugin not in declarations:
            issues.append(FunctionIssue(slot,'FUNCTION_SELECTED_ADAPTER_UNAVAILABLE',
                'Selected strategy has no matching-version mission adapter: ' + plugin))
    for function in rows:
        frontier = set(function['depends_on']); visited = set()
        for _step in range(33):
            if not frontier: break
            if function['instance_id'] in frontier:
                Add(function, 'FUNCTION_DEPENDENCY_CYCLE', 'Function dependency cycle'); break
            visited.update(frontier)
            frontier = {dependency for identity in frontier if identity in by_id
                        for dependency in by_id[identity]['depends_on'] if dependency not in visited}
    issues.extend(_TriggerIssues_Get(model,rows,declarations,resolution))
    return tuple(issues)


def _TriggerIssues_Get(model, functions, declarations, resolution):
    """Numeric signal producers come from a declared contract, never stage names."""
    if model.mission_process is None: return []
    contract=json.loads((_ROOT/'contracts/mission_functions_v1.json').read_text(encoding='utf-8'))
    stages=model.mission_process['stages'];stage_ids=[row['stage_id'] for row in stages]
    by_id={row['instance_id']:row for row in functions}
    selected=[model.strategies.get(slot) for slot in contract['condition_source_strategy_order']]
    selected_plugin=next((plugin for plugin in selected if plugin is not None),None)
    output=declarations.get(selected_plugin,{}).get('output')
    producers=[row for row in functions if row['output']==output]
    producer=producers[0] if len(producers)==1 else None
    result=[]
    for index,stage in enumerate(stages):
        signal=stage['condition']['signal']
        if signal not in contract['condition_signal_outputs']: continue
        if producer is None or output not in contract['condition_signal_outputs'][signal]:
            result.append(FunctionIssue('', 'FUNCTION_TRIGGER_INPUT_NOT_READY',
                f"{stage['stage_id']}: {signal} requires a unique configured canonical navigation output",
                stage_id=stage['stage_id']))
            continue
        start,stop=(BoundaryIndex_Get(producer[key],stage_ids) for key in ('start','stop'))
        if producer['start']['kind']=='mission_start':
            start=next((i for i,row in enumerate(stages) if row['condition']==
                {'signal':'event','operator':'is','value':'start_accepted','unit':'event_id'}),None)
        missing=any(row.consumer_component==producer['plugin_id'] for row in resolution.missing)
        if missing or producer['execution']!='continuous' or start is None or stop is None or start>=index or stop<index:
            result.append(FunctionIssue(producer['instance_id'],'FUNCTION_TRIGGER_INPUT_NOT_READY',
                f"{stage['stage_id']}: {signal} source is not proven available before entry-condition sampling",
                stage_id=stage['stage_id']))
        for function in functions:
            if function['start']!={'kind':'stage_enter','stage_id':stage['stage_id']}: continue
            frontier={producer['instance_id']};visited=set()
            for _step in range(33):
                if not frontier: break
                if function['instance_id'] in frontier:
                    result.append(FunctionIssue(function['instance_id'],'FUNCTION_TRIGGER_DEPENDENCY_CYCLE',
                        f"{stage['stage_id']}: entry condition {signal} requires output that waits for this same stage",
                        stage_id=stage['stage_id']))
                    break
                visited.update(frontier)
                frontier={dependency for identity in frontier if identity in by_id
                    for dependency in by_id[identity]['depends_on'] if dependency not in visited}
    return result


def FunctionsGeneration_Require(model, catalog):
    issues = Functions_Issues(model, catalog)
    if issues:
        raise ValueError('; '.join(f'{row.code}:{row.function_id}: {row.message}' for row in issues))


def ParameterProfile_Build(model, catalog, plugin_id):
    from silverstar_fccg.project.function_parameters import ParameterProfile_Build as Build
    return Build(model,catalog,plugin_id)


def ParameterProfile_Preview(model, catalog, plugin_id, value):
    from silverstar_fccg.project.function_parameters import ParameterProfile_Preview as Preview
    return Preview(model,catalog,plugin_id,value)


def ParameterProfile_Apply(model, catalog, plugin_id, value):
    from silverstar_fccg.project.function_parameters import ParameterProfile_Apply as Apply
    return Apply(model,catalog,plugin_id,value)


def ParameterProfile_Read(path):
    from silverstar_fccg.project.function_parameters import ParameterProfile_Read as Read
    return Read(path)


def ParameterProfile_Write(path,value,replace_existing=False):
    from silverstar_fccg.project.function_parameters import ParameterProfile_Write as Write
    return Write(path,value,replace_existing)
