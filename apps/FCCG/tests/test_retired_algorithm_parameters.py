from copy import deepcopy

import pytest

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.plugins.algorithm_parameters import AlgorithmParameters_Parse
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.pages.algorithm_parameters import AlgorithmParametersPage

KF = 'silverstar.algorithm.estimator.kf6'


def test_revision3_retained_parameters_are_read_only_and_overscale_rejected(builtin_catalog, qapp):
    owner = builtin_catalog.Component_Get(KF)
    retired = tuple(p for p in owner.algorithm_parameters if p.lifecycle == 'legacy_read_only')
    assert len(retired) == 6
    assert len([p for p in owner.algorithm_parameters if p.lifecycle == 'active']) == 30
    model = ReferenceProject_Create(catalog=builtin_catalog)
    legacy = retired[0]
    model.algorithm_parameters[KF][legacy.parameter_id] = 3.5
    page = AlgorithmParametersPage(Translator('en_US'))
    page.Configuration_Set((owner,), model.algorithm_parameters)
    assert all(page.editors[KF, p.parameter_id].isReadOnly() for p in retired)
    assert not page.editors[KF, 'gnss_integrity_position_r_scale'].isReadOnly()
    assert model.algorithm_parameters[KF][legacy.parameter_id] == 3.5
    model.algorithm_parameters[KF]['gnss_integrity_position_r_scale'] = 5.0
    with pytest.raises(ValueError, match=r'outside \[1.0, 4.0\]'):
        AlgorithmParameters_Resolve(model, builtin_catalog)
    assert model.algorithm_parameters[KF]['gnss_integrity_position_r_scale'] == 5.0
    page.close()


def test_unknown_parameter_lifecycle_is_rejected(builtin_catalog):
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_algorithm_estimator_kf6/plugin.json'
    metadata = deepcopy(json.loads(path.read_text(encoding='utf8'))['algorithm_parameters'])
    metadata['parameters'][0]['lifecycle'] = 'silently_ignore'
    with pytest.raises(ValueError, match='lifecycle'):
        AlgorithmParameters_Parse(metadata)
