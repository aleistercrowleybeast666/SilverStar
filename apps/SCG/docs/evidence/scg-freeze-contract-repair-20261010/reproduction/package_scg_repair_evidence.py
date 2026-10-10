from pathlib import Path
import json, shutil, hashlib

task=Path(__file__).parent
repo=task/'r'
data=json.loads((task/'SCG_FREEZE_CONTRACT_REPAIR_20261010.json').read_text(encoding='utf8'))
assert data['totals']['failed']==0, data['totals']
assert len(data['gates'])==28 and all(g.get('exit')==0 for g in data['gates']), 'Inspect every real gate exit before publishing summary'
assert all(g.get('source_commit',g.get('compile_source_commit'))==data['final_code_commit'] for g in data['gates']), 'Do not relabel old gate source versions'
assert data['startup']['exit']==0 and data['launcher']['exit']==0
native=data['artifact_evidence']['native_candidates']
unified=[row for row in native if row['index_label']=='srgui01']
assert {row['part'] for row in unified}=={'STM32F103C8T6','STM32C071FBP6'}
assert all(row['source_commit']==data['final_code_commit'] for row in unified)
assert all(row['command']['source_commit']==data['final_code_commit'] for row in data['complete_module_groups'])
assert all(row['tests']>0 and row['command']['exit']==0 for row in data['complete_module_groups'])
assert all(not row['warning_diagnostics'] for row in native)

dest=repo/'apps/SCG/docs/evidence/scg-freeze-contract-repair-20261010'
dest.mkdir(parents=True,exist_ok=True)
(dest/'.gitattributes').write_text('* -text\n',encoding='ascii')
baseline=dest/'baseline';baseline.mkdir(exist_ok=True)
runs=dest/'runs';runs.mkdir(exist_ok=True)
helpers=dest/'reproduction';helpers.mkdir(exist_ok=True)
for path in task.iterdir():
    if path.is_file() and path.name.startswith('fz') and path.suffix in {'.json','.jsonl','.log','.xml'}:
        shutil.copyfile(path,baseline/path.name)
    if path.is_file() and path.name.startswith(('sr','ds')) and path.suffix in {'.json','.jsonl','.log','.xml'}:
        shutil.copyfile(path,runs/path.name)
for name in ['SCG_FREEZE_VERIFICATION_20261010.json','SCG_FREEZE_VERIFICATION_20261010.md',
             'SCG_SIX_FAILURE_CLASSIFICATION_20261010.md','SCG_FREEZE_CHECKPOINT_20261010.md']:
    shutil.copyfile(task/name,baseline/name)
for name in ['SCG_REPAIR_HANDOFF_20261010.md','SCG_FREEZE_CONTRACT_REPAIR_20261010.json']:
    shutil.copyfile(task/name,dest/name)
shutil.copytree(task/'freeze-artifact-evidence',baseline/'artifacts',dirs_exist_ok=True)
shutil.copytree(task/'repair-artifact-evidence',dest/'artifacts',dirs_exist_ok=True)
dependencies=dest/'baseline-dependencies'
for name in data['dependency_and_p2_repair']['sparse_dependency_repair']['files']:
    source=repo/name;target=dependencies/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==data['dependency_and_p2_repair']['sparse_dependency_repair']['files'][name]['sha256']
for name in ['repair_backend_pytest.py','run_scg_repair_group.py','run_repair_sequence.py',
 'run_repair_usb_gui.py','run_repair_async.py','run_usb_candidate_gates.py',
 'repair_scg_startup_check.py','repair_scg_launcher.py','generate_scg_repair_legacy.py',
 'run_scg_repair_legacy_gate.py','run_repair_root_entry.py','collect_repair_private_index.py',
 'collect_repair_artifact_evidence.py','summarize_scg_repair.py','package_scg_repair_evidence.py',
 'run_repair_final_groups.py','run_repair_normalization.py','record_scg_dependency_repair.py',
 'correct_scg_startup_scope_metadata.py','resume_scg_d_final.py','relocate_scg_output_locators_d.py','refresh_scg_migration_quality.py','record_scg_runner_sideeffect.py','prepare_scg_evidence_d.py']:
    shutil.copyfile(task/name,helpers/name)
shutil.copyfile(Path(r'D:\python_software\SilverStar\docs\evidence\nightly_software_20261008\normal_test_paths.py'),helpers/'normal_test_paths.py')

for folder in ['ds-migration-locators','ds-migration-quality','ds-import-sideeffect']:
    shutil.copytree(task/folder,dest/folder,dirs_exist_ok=True)
metrics_dest=dest/'async-final-response';metrics_dest.mkdir(exist_ok=True)
for row in data['async_final_response_metrics']:
    shutil.copyfile(row['file'],metrics_dest/(row['data']['part']+'.json'))
review=Path('D:/Codex_Work/2026-10-09/task-2/scg-review-819-catalog')
review_dest=dest/'ordinary-catalog-review-819';review_dest.mkdir(exist_ok=True)
for name in ['command.json','tests.log','tests.xml','review.md']:
    if (review/name).is_file():shutil.copyfile(review/name,review_dest/name)
shutil.copyfile(Path('D:/Codex_Work/migration-ledgers/scg-owned-processes-cancelled.json'),dest/'scg-owned-processes-cancelled.json')

lines=['# SCG freeze contract repair - final software evidence, 2026-10-10','',
 'Code base: `'+data['base_commit']+'`. Main repair: `'+data['main_repair_commit']+'`.',
 'Final code: `'+data['final_code_commit']+'`; isolated branch `'+data['branch']+'`.',
 'Worktree: `'+data['worktree']+'`. No merge/push/tag/publication or hardware action.','',
 '## Six-failure classification and repair','',
 '| Original failure | Actual repair and final evidence |', '| --- | --- |',
 '| F103 full model equality | Positive fixture uses the actual unified importer and pinned authority. Full equality assertion retained. Complete backend modules pass. |',
 '| F103 unified Export/Build from legacy facts | Explicit legacy preflight refusal before output/worker/SaveAs. GUI, refresh and Plan agree; actionable original CubeMX source reimport is exercised through save/reload and real UI. Old identities and pinned hashes are not rewritten. F103 first-batch actual build passes. |',
 '| Duplicate physical facts in platform variants | Production Scan accepts duplicate hardware only with proven finite disjoint exact MCU-part domains from mandatory dependencies. Overlap, missing, optional, broad and wildcard domains reject. Full platform identity/cache/security and round2 modules pass. |',
 '| Importer tools package missing from test entry | Pyproject exposes application root and src. Direct root python -m pytest without import shim or PYTHONPATH passes both original importer/doc cases. Full runtime module passes. |',
 '| Documentation replay destination policy | Test destination has destination-root WorkspacePolicy. Guard, byte idempotence and heading-count assertions retained; full runtime module passes. |',
 '| Stack-report overlay stale | Overlay matches the existing authoritative core payload byte-for-byte: SHA256 8de5e90798c76a53c3acd3f178726cf6d0a94ed06b996ea717e892748c23bb47. No allowlist/hash/limit expanded. Full runtime and stack modules plus generated artifact targets pass. |','',
 '## Complete affected modules','',
 '| Run | Passed | Failed | Skipped | Source commit |','| --- | ---: | ---: | ---: | --- |']
for row in data['complete_module_groups']:
    lines.append('| '+row['label']+' | '+str(row['passed'])+' | '+str(len(row['failed']))+' | '+str(len(row['skipped']))+' | `'+row['command']['source_commit']+'` |')
t=data['totals']
lines+=['',f"Total: **{t['passed']} passed, {t['failed']} failed, {t['skipped']} skipped**, {t['tests']} explicit affected-scope cases.",
 'Additional direct root entries: srentry02 two cases; D entry ds-entry01 sixteen cases. Not counted in complete-module totals. Earlier source-version runs are not counted twice.',
 'This covers every case in the recorded complete affected modules, not all SCG test files.','',
 'Every final complete group, final first-batch F103/C071 receipt and final private',
 'F103/F407 build/gate runs at `'+data['final_code_commit']+'`. Earlier a0afca6 and',
 '24462e4 runs remain separately archived, with their actual source identities.','',
 'Ordinary review of 24462e4 found a further catalog P2: case/separator spellings',
 'could appear disjoint despite matching one runtime MCU. The original matcher token',
 'function body is unchanged and shared from core/platform_tokens.py. Catalog domain',
 'sets, collision owners and identity keys use that same rule; empty canonical tokens',
 'remain rejected. Three equivalent spellings reject in actual Scan before publication,',
 'with runtime equivalence proved; distinct normalized model and original negatives pass.',
 'Complete physical identity and internal platform refactor modules run in final Flight.','',
 '## First-batch actual F103/C071 evidence','',
 '| API / part | Normal + analyzer executed commands | Recorded warning diagnostics | Source commit |','| --- | ---: | ---: | --- |']
for row in native:
    if row['index_label'] not in {'srgui01','srprivate02'}: continue
    lines.append('| '+('Unified first-batch' if row['index_label']=='srgui01' else 'Private regression')+' / '+row['part']+' | '+str(row['commands_executed'])+' | '+str(len(row['warning_diagnostics']))+' | `'+row['source_commit']+'` |')
lines+=['','Private F407 is a regression only; it does not substitute for first-batch C071.',
 'The archive contains each actual compile/backend receipt, normal/analyzer ELF and',
 'vector bytes with hashes. CPU/IRQ architecture and artifact checks use the actual',
 'candidate and independent SDK evidence; no hardware behavior is claimed.','',
 'All **28 original software gate commands returned 0**: private F103/F407 eight,',
 'unified F103/C071 eight, fresh Flight/GroundUART twelve (PoT, architecture, Host,',
 'normal ARM, analyzer, artifact). Actual launcher and Qt startup/normal shutdown passed.','',
 '## Preserved baselines, skips and warnings','',
 'Original baseline: **560 passed, 6 failed, 12 skipped**. All raw original logs,',
 'commands, classification and compact artifacts remain under `baseline/`. Initial',
 'repair trial srpre01 retains 11 passes and one new fixture setup failure: settings',
 'outside the service workspace. The fixture was corrected without relaxing policy;',
 'srpre02 and the final complete GUI group pass. Initial Flight srf01 retains',
 '215 passes, five failures and ten skips: sparse checkout lacked the unchanged GSHC',
 'parser and two committed historical fixtures. Actual failure tracebacks and exact',
 'Git/SHA256 identities are retained; the original test bodies run on checked-out',
 'baseline dependencies in final Flight, with no GSHC code change or test redirect.',
 'P2 precommit srnorm01 retains an import-cycle error before collection. Moving the',
 'shared function from hardware to core corrects that dependency; srnorm02 fourteen',
 'checks pass, and final complete groups rerun afterward. Receipt discovery initially included',
 'unified receipts, then was corrected using actual unified index exclusion; product',
 'code and gate behavior were unchanged.','',
 'sra01 retains two synchronous rendering threshold failures: 0.7795494 / 0.8358071',
 'seconds versus the unchanged 0.75 second bound while the owned backend compile',
 'sequence was active. Final ds-async03 runs the entire unchanged async module serially',
 'after verified migration and actual quality rechecks. No threshold/skip/xfail was changed.',
 'Final sync refresh: F103 0.528781 seconds; C071 0.526871 seconds (< original 0.75).',
 'Max Qt interval: 0.074654/0.083199 seconds (< original 0.5), 57/83 ticks, one',
 'Plan each on the worker. Exact measured JSON bytes are in async-final-response/.',
 'Serial GUI responsiveness evidence does not guarantee timing under unrelated',
 'concurrent heavy compile load; the prior failures remain visible for review.','',
 'C-disk emergency interrupted srf02 and Flight analyzer without completed outcomes.',
 'The independent migration task terminated all fourteen owned paused processes.',
 'D continuation preserves completed source-819 evidence and reuses actual generated',
 'Flight output; static-analysis forces a complete serial recompile; artifact is',
 'the original target. New TEMP/TMP/logs remain on D with an 8 GiB stop threshold.',
 'ds-async01 preserves 12 passes/four alias refusals in original XML. Updating only',
 'verified output locators leaves model/receipt/ELF hashes unchanged. ds-async02',
 'preserves 14 passes/two stale record failures because the pointer path is part of',
 'the real input digest. Original quality records are saved; actual architecture',
 'and artifact operations regenerate new records with no stale/hash guard bypass.',
 'Ordinary independent review of 819 closes catalog P2: six tests, exit 0, unchanged',
 'HEAD/source hashes/clean worktree, archived under ordinary-catalog-review-819.',
 'Evidence limitation: importing the orchestration helper accidentally reran entry',
 'and aborted async before collection due existing basetemp, overwriting two early',
 'D logs/command files. The original failed async XML and initial sequence metadata',
 'remain; original log bytes are unavailable. Sideeffect files and correction record',
 'are archived; no product code or test body was changed. The runner now has a',
 'main guard. Final ds-async03 command/log/XML are separate complete evidence.',
 '', 'Skip explanations (original test assertions remain):','']
for row in data['complete_module_groups']:
    for skip in row['skipped']:
        lines.append('- `'+skip['name']+'`: '+skip['reason'])
lines+=['','The ten artifact-protocol fixture cases require explicitly supplied independent',
 'maintenance-enabled/disabled real Release roots; this run does not supply that pair.',
 'Fresh generated Flight artifact-check is separately executed and is not counted as',
 'passing these skipped cases. Previously skipped private Native build cases now ran.',
 'Wrapped pytest runs retain the pre-existing cache_dir warning after disabling',
 'cacheprovider. Original srentry02 direct root entry has no such warning; D entry',
 'ds-entry01 disables cacheprovider and retains that warning. Native receipts have',
 'zero warning diagnostics. Legacy diagnostics are preserved without claiming a zero-warning gate:','']
for row in data['artifact_evidence']['legacy_log_diagnostics']:
    if row['warnings']:
        lines.append('- `'+row['target']+'`: '+str(len(row['warnings']))+' warning lines; see exact log.')
lines+=['','## Reviewable freeze scope and remaining limits','',
 'Candidate for ordinary review/integration: these six contract/test-source repairs',
 'plus the subsequently reported catalog normalization P2 closure,',
 'the current private first-batch F103/C071 software workflows and verified emitted',
 'normal gates. Parent owns independent ordinary review and serial SCG/GSHC/FLP integration.',
 'No daily merge or freeze approval has been performed. UI widgets/layout, flight math,',
 'FINAL, GSHC/FLP and daily source remain outside this edit scope.','',
 '**Formal USB release remains BLOCKED.** b66 independent safety review is',
 '**NO_PASSED_OUTCOME**, has not been retried/bypassed and is not marked reviewed.',
 "No malformed USB/owner-expression research was executed. PoT uses the project's",
 'F Prime-inspired text adaptation; critical-contract acceptance **NOT PROVEN**.',
 'Whole-program stack/WCET, PCD/IRQ physical scheduling and hardware remain outside',
 'software evidence. Passing builds does not admit generic unknown configurations.',
 'Original guards, assertions, source identity hashes and limits remain intact.','',
 'Evidence directory: `docs/evidence/scg-freeze-contract-repair-20261010/`.',
 'Reproduction scripts retain actual original absolute paths and source inputs; use',
 'the recorded D process environment/migration maps for continuation. They are',
 'evidence of exact executed commands, not a self-contained vendor distribution.',
 'The manifest hashes original saved bytes; its local `* -text` attributes preserve',
 'new evidence bytes in Git and do not modify source attributes or admission identities.']
lines+=['','The original startup record retained an inaccurate inherited daily/merged scope',
 'phrase. Its metadata correction names the actual isolated checkout and preserves',
 'the original record/hash; all source identities, timestamps and results are unchanged.']
report=repo/'apps/SCG/docs/SCG_FREEZE_CONTRACT_REPAIR_20261010.md'
report.write_text('\n'.join(lines)+'\n',encoding='utf8')
shutil.copyfile(report,dest/'FINAL_REPORT.md')
manifest={path.relative_to(dest).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
          for path in sorted(dest.rglob('*')) if path.is_file() and path.name!='SHA256_MANIFEST.json'}
(dest/'SHA256_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(json.dumps({'evidence':str(dest),'files':len(manifest),'bytes':sum(p.stat().st_size for p in dest.rglob('*') if p.is_file()),
 'manifest_sha256':hashlib.sha256((dest/'SHA256_MANIFEST.json').read_bytes()).hexdigest(),
 'aggregate_sha256':hashlib.sha256((task/'SCG_FREEZE_CONTRACT_REPAIR_20261010.json').read_bytes()).hexdigest()},indent=2))
