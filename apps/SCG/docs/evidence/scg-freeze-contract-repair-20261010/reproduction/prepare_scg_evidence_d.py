from pathlib import Path
T=Path(__file__).parent
p=T/'summarize_scg_repair.py';s=p.read_text()
s=s.replace("'srf02','srgui01','sra02'","'ds-flight01','srgui01','ds-async03'")
s=s.replace("'srentry01','sra01'","'srentry01','sra01','ds-async02'")
s=s.replace("extra=[suite('srentry02')]","extra=[suite('srentry02'),suite('ds-entry01')]")
s=s.replace("daily=Path(r'D:","for label in ['ds-Flight-static-analysis','ds-Flight-artifact-check']:\n    gates.append({'label':label,**json.loads((task/(label+'-command.json')).read_text())})\n\ndaily=Path(r'D:")
s=s.replace("'final_groups_sequence':", "'D_migration_locator':json.loads((task/'ds-locator-migration.json').read_text()),\n 'D_migration_quality':json.loads((task/'ds-migration-quality.json').read_text()),\n 'evidence_correction':json.loads((task/'ds-evidence-correction.json').read_text()),\n 'D_original_failed_sequence':json.loads((task/'ds-resume-sequence.json').read_text()),\n 'D_alias_failure_original_xml':suite('ds-async01'),\n 'migration_process_cancellation':json.loads(Path('D:/Codex_Work/migration-ledgers/scg-owned-processes-cancelled.json').read_text(encoding='utf-8-sig')),\n 'ordinary_catalog_review_819':json.loads(Path('D:/Codex_Work/2026-10-09/task-2/scg-review-819-catalog/command.json').read_text()),\n 'final_groups_sequence':")
s=s.replace("'limits':[", "'limits':[\n  'C disk emergency interrupted srf02 and Flight analyzer without completion. Independent migration task terminated old owned processes; original ledgers retained. D serial continuation finishes only named remaining checks.',\n  'ds-async01 retained 12 passes/4 alias refusal failures in original XML. ds-async02 retained 14 passes/2 correct stale quality failures after pointer relocation. Actual product APIs regenerated quality results, preserving old records and immutable model/receipt/ELF bytes.',\n  'Evidence helper import sideeffect overwrote two early D raw logs/command files. Original failed async XML and original sequence metadata/hash survive; raw original log bytes unavailable. This limitation is explicitly archived, not silently relabeled.',")
p.write_text(s)
p=T/'collect_repair_artifact_evidence.py';s=p.read_text()
s=s.replace("for row in map(json.loads,(task/(label+'-build-index.jsonl')).read_text().splitlines()):", "for row in map(json.loads,(task/('ds-migrated-build-index.jsonl' if label=='srgui01' else label+'-build-index.jsonl')).read_text().splitlines()):")
s=s.replace("for path in sorted(task.glob('srlegacy-'+row['kind']+'-*.log')):","log_paths=list(task.glob('srlegacy-'+row['kind']+'-*.log'))\n if row['kind']=='Flight':log_paths += list(task.glob('ds-Flight-*.log'))\n for path in sorted(log_paths):")
p.write_text(s)
