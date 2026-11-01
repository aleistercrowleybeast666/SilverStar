"""Explicit software research scheduling, separate from mathematical core inclusion."""
from copy import deepcopy
import math

OUTPUT = 'control.research.command'
PERIOD_US = 10000


def ControlResearchBinding_Require(model, catalog):
    rows = [row for row in (model.mission_functions or {}).get('functions', []) if row['output'] == OUTPUT]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError('FUNCTION_CONTROL_SINGLETON')
    row = rows[0]
    if row['plugin_id'] not in ('silverstar.algorithm.control.pid', 'silverstar.algorithm.control.lqr'):
        raise ValueError('FUNCTION_CONTROL_OWNER')
    if row['plugin_id'] not in model.ComponentIds_Get():
        raise ValueError('FUNCTION_CONTROL_NOT_SELECTED')
    from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve
    values = AlgorithmParameters_Resolve(model, catalog)
    # Resolve through the same actual-value authority used by the generated header.
    owner = next(item for item in values if item['component'] == row['plugin_id'])
    parameters = {item['id']: item['value'] for item in owner['parameters']}
    if row['plugin_id'].endswith('.pid') and not math.isclose(parameters['sample_period_s'], .01, rel_tol=0, abs_tol=1e-9):
        raise ValueError('FUNCTION_CONTROL_PERIOD_REQUIRES_10_MS')
    if not 0 < parameters['output_limit'] <= 1:
        raise ValueError('FUNCTION_CONTROL_TORQUE_LIMIT_MAXIMUM_1_NM')
    return deepcopy(row)


def ControlResearch_Attach(model, catalog):
    """Opt in the single selected core to the bounded research mission consumer."""
    from silverstar_fccg.project.mission_functions import Function_Create, Functions_Derive, FunctionsGeneration_Require
    selected = [identity for identity in model.ComponentIds_Get() if identity in
                ('silverstar.algorithm.control.pid', 'silverstar.algorithm.control.lqr')]
    if len(selected) != 1:
        raise ValueError('FUNCTION_CONTROL_SELECT_ONE_CORE')
    candidate = deepcopy(model)
    functions = Functions_Derive(candidate, catalog)
    controllers = [row for row in functions['functions'] if row['output'] == OUTPUT]
    if not controllers:
        functions['functions'].append(Function_Create(selected[0], catalog))
    elif len(controllers) != 1 or controllers[0]['plugin_id'] != selected[0]:
        raise ValueError('FUNCTION_CONTROL_OWNER')
    candidate.mission_functions = functions
    FunctionsGeneration_Require(candidate, catalog)
    return candidate
