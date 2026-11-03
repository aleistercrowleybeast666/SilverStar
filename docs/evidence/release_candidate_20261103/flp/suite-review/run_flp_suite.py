"""Run FLP with recorded per-case deadlines and explicit continuation ranges."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    options = argparse.ArgumentParser()
    options.add_argument('--repo', type=Path, required=True)
    options.add_argument('--work', type=Path, required=True)
    options.add_argument('--evidence', type=Path, required=True)
    options.add_argument('--tag', required=True)
    options.add_argument('--case-seconds', type=int, default=150)
    options.add_argument('--max-continuations', type=int, default=8)
    options.add_argument('nodes', nargs='*')
    args = options.parse_args()
    evidence = args.evidence.resolve(); repo = args.repo.resolve(); work = args.work.resolve()
    work.mkdir(exist_ok=True, parents=True)
    evidence.mkdir(exist_ok=True, parents=True)
    script = Path(__file__).resolve().parent
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1', PYTHONUTF8='1',
               SS_FLP_CASE_SECONDS=str(args.case_seconds))
    env['PYTHONPATH'] = os.pathsep.join(map(str, [script, repo/'apps/FLP/src', repo/'apps/FLP', repo/'apps/SCG/src']))
    remaining = list(args.nodes); receipts = []; seen = set()
    for part in range(args.max_continuations + 1):
        key = args.tag + '-' + str(part + 1)
        journal = evidence/(key+'.jsonl'); log = evidence/(key+'.log'); xml = evidence/(key+'.xml')
        if journal.exists() or log.exists():
            raise FileExistsError(key)
        env['SS_FLP_JOURNAL'] = str(journal)
        selection = remaining or ['tests']
        if len(selection) > 20:
            # Pytest reads one node per line. This preserves exact IDs without
            # exceeding the Windows process command-line length on a resume.
            selected = evidence / (key+'-nodes.txt')
            selected.write_text('\n'.join(selection)+'\n', encoding='utf8')
            selection = ['@'+str(selected)]
        cmd = [sys.executable, '-B', '-u', '-m', 'pytest', '-p', 'flp_case_watch', '-v', '--tb=short',
               '--disable-warnings', '--junitxml='+str(xml), '-o', 'cache_dir='+str(work/('c'+str(part))),
               '--basetemp='+str(work/str(part)), *selection]
        start = time.monotonic()
        with log.open('w', encoding='utf8') as output:
            run = subprocess.run(cmd, cwd=repo/'apps/FLP', env=env, stdout=output, stderr=subprocess.STDOUT)
        events = [json.loads(line) for line in journal.read_text(encoding='utf8').splitlines()] if journal.exists() else []
        collected = next((row['ids'] for row in events if row['event']=='collection'), [])
        started = [row['node'] for row in events if row['event']=='start']
        finished = [row['node'] for row in events if row['event']=='finished']
        phases = {(row['node'], row['phase']):row['result'] for row in events if row['event']=='phase'}
        assert not (seen & set(started)), 'A continuation repeated a started test'
        seen.update(started)
        left = [node for node in collected if node not in seen]
        receipt = dict(command=cmd, cwd=str(repo/'apps/FLP'), python=sys.version, source_base=os.environ.get('SS_FLP_SOURCE', ''),
                       elapsed=round(time.monotonic()-start,2), exit=run.returncode,
                       case_seconds=args.case_seconds, collected=len(collected), started=len(started), finished=len(finished),
                       interrupted=sorted(set(started)-set(finished)), untouched=len(left),
                       phases={status:sum(result==status for result in phases.values()) for status in ('passed','failed','skipped')},
                       junit_written=xml.exists(), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(), journal=journal.name)
        receipts.append(receipt)
        (evidence/(args.tag+'-receipts.json')).write_text(json.dumps(receipts, indent=2)+'\n', encoding='utf8')
        print(key, receipt['exit'], 'finished',len(finished),'interrupted',receipt['interrupted'],'untouched',len(left),flush=True)
        if not left or not started:
            break
        remaining = left
    return int(any(row['exit'] for row in receipts))


if __name__ == '__main__':
    raise SystemExit(main())
