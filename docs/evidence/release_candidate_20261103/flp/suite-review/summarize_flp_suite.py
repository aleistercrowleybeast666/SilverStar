"""Count original tests once. Focused retries are reported separately."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def read_events(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def main():
    folder = Path(__file__).resolve().parent
    first = folder/'full-bounded-1.jsonl'
    tracks = [first, *sorted(folder.glob('continued-*.jsonl'),
                             key=lambda path: int(path.stem.rsplit('-', 1)[1]))]
    seen = {}; phases = defaultdict(dict); outcomes = {}; segments = []
    collected = next(row['ids'] for row in read_events(first) if row['event'] == 'collection')
    originals = set(collected)
    for journal in tracks:
        rows = read_events(journal)
        started = [row['node'] for row in rows if row['event'] == 'start']
        finished = {row['node'] for row in rows if row['event'] == 'finished'}
        for node in started:
            if node not in originals or node in seen:
                raise ValueError('Unexpected or repeated initial-suite node: '+node)
            seen[node] = journal.name
        for row in rows:
            if row['event'] == 'phase':
                phases[row['node']][row['phase']] = row
        counts = Counter()
        for node in started:
            stage = phases[node]
            if node not in finished:
                status = 'interrupted'
            elif any(stage.get(part, {}).get('result') == 'failed' for part in ('setup','teardown')):
                status = 'error'
            elif stage.get('call', {}).get('result') == 'failed':
                status = 'failed'
            elif any(phase['result'] == 'skipped' for phase in stage.values()):
                status = 'skipped'
            elif stage.get('call', {}).get('result') == 'passed':
                status = 'passed'
            else:
                raise ValueError('Incomplete phase classification: '+node)
            counts[status] += 1
            outcomes[node] = status
        segments.append({'journal':journal.name,'started':len(started),'finished':len(finished),
                         'distinct_test_outcomes':dict(counts), 'interrupted':sorted(set(started)-finished)})
    unstarted = sorted(originals-set(seen))
    summary = {'reference_collection':len(collected),'distinct_started':len(seen),
               'unstarted':unstarted,'distinct_original_outcomes':dict(Counter(outcomes.values())),
               'segments':segments,'scope':'Disjoint first attempts on original collection. Separate processes and source epochs; no single completed passing suite.'}
    by_file = defaultdict(Counter)
    for node, status in outcomes.items():
        by_file[node.split('::')[0]][status] += 1
    summary['by_file'] = {key:dict(value) for key,value in sorted(by_file.items())}
    failures = []
    for node, outcome in outcomes.items():
        if outcome == 'passed':
            continue
        statuses = phases[node]
        errors = [row for row in statuses.values() if row['result'] in ('failed','skipped')]
        failures.append({'node':node,'status':outcome,'segment':seen[node],
                         'phases':{key:val['result'] for key,val in statuses.items()},
                         'first_error_lines':[line for row in errors for line in row['reason'].splitlines()
                                              if line.startswith('E   ')][:4]})
    (folder/'nonoverlap-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (folder/'nonpasses.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(summary['distinct_original_outcomes'], 'unstarted', len(unstarted))


if __name__ == '__main__':
    main()
