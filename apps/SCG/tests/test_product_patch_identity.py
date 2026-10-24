from copy import deepcopy
import pytest
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.app.version import SILVERSTAR_BUILD_ID, SILVERSTAR_PLATFORM_VERSION


@pytest.mark.parametrize('previous', ['0.1.0', '0.1.1'])
def test_old_official_patch_opens_in_memory_without_rewriting_input(builtin_catalog, previous):
    data = ReferenceProject_Create(catalog=builtin_catalog).Dictionary_Get()
    data['project']['firmware_version'] = previous
    data['project']['build_target'] = 'SilverStar_' + previous.replace('.', '_')
    original = deepcopy(data)
    loaded = ProjectModel_Parse(data)
    assert data == original
    assert loaded.identity.firmware_version == SILVERSTAR_PLATFORM_VERSION
    assert loaded.identity.build_target == SILVERSTAR_BUILD_ID
    assert loaded.device_instances == ProjectModel_Parse(original).device_instances
    assert loaded.Dictionary_Get()['log_decoder_profile'] == data['log_decoder_profile']
    assert ProjectConfiguration_Reconcile(loaded, builtin_catalog).edit_validation.valid
