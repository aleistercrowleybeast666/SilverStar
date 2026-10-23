from pathlib import Path
import json, runpy
import pytest
ROOT=Path(__file__).resolve().parents[2]
API=runpy.run_path(str(ROOT/'tools/silverstar_version.py'))

def test_checkout_inventory_exposes_missing_development_sources():
    report=API['VersionInventory_Resolve'](ROOT)
    assert report['product']==(ROOT/'VERSION').read_text().strip()
    assert report['identities']['SCG']['value']==report['identities']['FLP']['value']==report['identities']['GSHC']['value']==report['product']
    assert report['records'] and report['plugins']
    for key in ('AIR','installation','navigation.journal'):
        row=report['identities'][key]
        if not (ROOT/json.loads((ROOT/'versions.json').read_text())['identities'][key]['source']['path']).exists():
            assert row['value'] is None and row['status']=='source_unavailable'

def test_optional_identity_does_not_hide_malformed_or_required_source(tmp_path):
    manifest=json.loads((ROOT/'versions.json').read_text())
    manifest['identities']={'test':{'scope':'test','source_required':False,
        'source':{'path':'source.json','kind':'json','selector':['version']}}}
    (tmp_path/'versions.json').write_text(json.dumps(manifest))
    (tmp_path/'VERSION').write_text('0.1.3')
    (tmp_path/'source.json').write_text('{invalid')
    with pytest.raises(ValueError):API['VersionInventory_Resolve'](tmp_path)
    manifest['identities']['test']['source_required']=True
    manifest['identities']['test']['source']['path']='missing.json'
    (tmp_path/'versions.json').write_text(json.dumps(manifest))
    with pytest.raises(FileNotFoundError):API['VersionInventory_Resolve'](tmp_path)
