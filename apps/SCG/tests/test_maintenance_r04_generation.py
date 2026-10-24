"""Maintenance frame capacity and explicit test identity survive generation."""
from dataclasses import replace
import json

import pytest

from silverstar_fccg.generator.render import GeneratedFiles_Render, _TestBuildIdentity_Get
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_maintenance_capacity_keeps_legacy_reply_and_other_uart_budgets(builtin_catalog):
    model = ReferenceProject_Create('MaintenanceCapacity', catalog=builtin_catalog)
    files = GeneratedFiles_Render(model, builtin_catalog, SourceGraph_Resolve(model, builtin_catalog))
    text = files['Generated/Inc/project_resources.h'].decode()
    assert '#define PROJECT_PLATFORM_UART_3_TX_RING_SIZE 4096U' in text
    assert '#define PROJECT_PLATFORM_UART_3_TX_PRIORITY_SIZE 1024U' in text
    assert '#define PROJECT_PLATFORM_UART_3_RX_DMA_SIZE 128U' in text
    assert '#define PROJECT_PLATFORM_UART_1_TX_RING_SIZE 192U' in text


def test_test_identity_is_opt_in_and_does_not_replace_navigation_declarations(builtin_catalog):
    model = ReferenceProject_Create('MaintenanceIdentity', catalog=builtin_catalog)
    model.identity = replace(model.identity, firmware_version='0.1.3')
    graph = SourceGraph_Resolve(model, builtin_catalog)
    before = GeneratedFiles_Render(model, builtin_catalog, graph)
    header = before['Generated/Inc/project_flight_config.h']
    assert b'product_version=0.1.3 maturity=development' in header
    assert b'kind=test' not in header
    model.reference_provenance = {'commit': 'a'*40, 'test_build': {
        'id': 'MERGE_SOFTWARE_ONLY', 'build_number': 4, 'build_tag': 'SST013R4'}}
    files = GeneratedFiles_Render(model, builtin_catalog, graph)
    header = files['Generated/Inc/project_flight_config.h'].decode()
    assert 'test_id=MERGE_SOFTWARE_ONLY' in header
    assert '#define SILVERSTAR_VERSION_BUILD' in header
    semantics = json.loads(files['Generated/project_semantics.json'])['metadata_declarations']
    assert semantics['software_test_build']['source_commit'] == 'a'*40
    old = json.loads(before['Generated/project_semantics.json'])['metadata_declarations']
    assert {k:v for k,v in semantics.items() if k != 'software_test_build'} == old


@pytest.mark.parametrize('change', [
    {'id': 'bad\"identity'}, {'build_number': True}, {'build_number': 256},
    {'build_tag': 'TOO_LONG_TAG'}, {'extra': 'unowned'},
])
def test_invalid_test_identity_rejects_before_render(builtin_catalog, change):
    model = ReferenceProject_Create('InvalidTestIdentity', catalog=builtin_catalog)
    model.reference_provenance = {'commit': 'a'*40, 'test_build': {
        'id': 'VALID_ID', 'build_number': 4, 'build_tag': 'SST013R4', **change}}
    with pytest.raises(ValueError):
        _TestBuildIdentity_Get(model)
