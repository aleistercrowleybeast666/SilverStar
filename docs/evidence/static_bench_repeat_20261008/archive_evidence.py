from pathlib import Path
import json, hashlib, subprocess, re, datetime
out=Path(__file__).resolve().parent
repo=out.parents[1]
dest=repo/'docs/evidence/static_bench_repeat_20261008'
assert not dest.exists(),'Never overwrite completed evidence'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=repo/'docs/evidence/static_bench_authorized_20261008'
sources=json.loads((old/'source_apps_sha256.json').read_text(encoding='utf-8'))
assert all(sha(repo/p)==h for p,h in sources.items())
prior_manifest=json.loads((old/'manifest.json').read_text(encoding='utf-8'))
roots=prior_manifest['root_inventory_inputs_preserved']
assert all(sha(repo/p)==h for p,h in roots.items())
old_mission=json.loads((old/'mission_static_01/result.json').read_text(encoding='utf-8'))
new=json.loads((out/'mission_repeat_01/result.json').read_text(encoding='utf-8'))
assert new['mission_result']=='COMPLETED_OBSERVED_SEQUENCE' and all(new['functional_checks'].values())
assert not new['sample_errors'] and new['flashes']==0 and new['resets']==1
identity=json.loads((out/'identify_result.json').read_text(encoding='utf-8'))
reset=json.loads((out/'reset_result.json').read_text(encoding='utf-8'))
assert identity['exact_readback_match'] and identity['exit_code']==reset['exit_code']==0
assert sha(out/'current_image_readback.bin')==identity['readback_sha256']
def row(d):
 return {'mission':d['mission_id']['value'],'state_reject':d['logger_bus']['state_reject_count'],'tx_dropped':d['radio_stats']['tx_dropped'],'tx_ok':d['radio_stats']['tx_ok'],'max_interval_us_scalar_observation':d['timing']['max_interval_us'],'timing_whole_snapshot_coherent':d['timing_coherent'],'accepting':d.get('accepting',{}).get('value'),'finalization':d.get('finalization',{}).get('value'),'state_before':d.get('STATE_BEFORE'),'state_after':d.get('STATE_AFTER')}
comparison={'000044':{name:row(json.loads((old/('diag_'+name)/'result.json').read_text(encoding='utf-8'))['decoded']) for name in ['before_unlock','after_start_live','postmission']},'000045':{name:dict(row(s['decoded']),utc_start=s['utc_start'],utc_end=s['utc_end'],elapsed_s=s['elapsed_s']) for name,s in new['samples'].items()},'limitations':['Counters reset for new boot; compare stage changes, not absolute cross-boot subtraction.','000044 final uses postmission halt, 000045 final is live and sampled earlier after landing.','All five 000045 whole timing blocks fail equal-even sequence coherence; report max fields as scalar observations.','State brackets stable do not make every dynamic field atomic.','No actual TF bytes or end-to-end wireless delivery proof.']}
(out/'comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
dest.mkdir()
records=[]
for p in sorted(out.rglob('*')):
 if not p.is_file() or '__pycache__' in p.parts or p.name=='current_image_readback.bin':continue
 rel=p.relative_to(out);target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
 target.write_bytes(p.read_bytes());assert sha(target)==sha(p)
 records.append({'path':rel.as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
(dest/'.gitattributes').write_text('* -text\n',encoding='ascii')
(dest/'source_apps_sha256.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
records.append({'path':'source_apps_sha256.json','bytes':(dest/'source_apps_sha256.json').stat().st_size,'sha256':sha(dest/'source_apps_sha256.json')})
doc=repo/'docs/STATIC_BENCH_REPEAT_20261008.md'
links=[]
for x in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
 if ':' in x or x.startswith('#'):continue
 target=(doc.parent/x.split('#')[0]).resolve()
 links.append({'link':x,'exists':target.exists() or target==dest/'manifest.json'})
assert all(x['exists'] for x in links)
manifest={'source_commit':'cac7bd29bf6f6aec5297715ea14893b4b7684953','starting_document_head':'87d98e598db5706a2d23d09e64ef0d77e1af8f90','branch':'fix/nightly-user-ready-20261003','recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_files':len(sources),'root_inventory_inputs_preserved':roots,'actual_execution':{'identity_exit':0,'exact_BIN_match':True,'reset_exit':0,'reset_count':1,'flash_count':0,'START_count':1,'retry_count':0,'static_script_exit':0,'mission':45,'connections_closed':True,'halts':0,'all_five_timing_whole_snapshots_coherent':False},'checks':{'finite_lifecycle_and_close':'PASS','logger_reject_class_recurrence':'REPRODUCED; 1 post-stop, previously 2','SX1281_enqueue_rejections':'REPRODUCED','about_94_3ms_preSTART_scalar_max_interval':'OBSERVED_AGAIN; whole timing coherence NOT_PROVEN','TF_persistent_bytes':'NOT_PROVEN','FLP_strict_recorded_open_save_reopen':'NOT_RUN','rejected_record_identity':'NOT_PROVEN','wireless_end_to_end_delivery':'NOT_PROVEN','max_interval_cause':'NOT_PROVEN'},'files':records,'retained_readback':{'path':str(out/'current_image_readback.bin'),'sha256':sha(out/'current_image_readback.bin'),'bytes':(out/'current_image_readback.bin').stat().st_size},'exact_decoder':prior_manifest['artifact_identity']['decoder'],'links':links,'evidence_limitations':['Process command line enumeration denied by local environment; name enumeration only found no matching other test processes. No permission changes.','Static script exit0 independently observed in exec session13489; later manifest creation is not an invented execution timestamp.','No second repetition, firmware change, test gate relaxation, TF substitution or cleanup.']}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'source_files':len(sources),'files':len(records),'links_ok':len(links),'mission':45,'whole_timing_coherent':False},indent=2))
