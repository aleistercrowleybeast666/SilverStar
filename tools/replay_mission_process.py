"""Execute a declared mission process offline; never sends hardware commands."""
import argparse
import json
from pathlib import Path

from silverstar_mission_profile import (MissionProfile_Read, MissionProcessRunner,
                                       MissionTrace_Write, _Pairs_Require)


def MissionProcess_Main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('samples', type=Path, help='JSONL authoritative event/numeric samples; MCU-monotonic microseconds')
    parser.add_argument('output', type=Path, help='New .ssmissiontrace path')
    parser.add_argument('--session', default='offline_reference')
    args = parser.parse_args()
    try:
        profile = MissionProfile_Read(args.profile)
        if 'process' not in profile:
            raise ValueError('mission_process_not_declared')
        runner = MissionProcessRunner(profile['process'])
        events = []
        with args.samples.open(encoding='utf-8') as source:
            for index in range(10001):
                line = source.readline(16385)
                if not line:
                    break
                if index == 10000 or len(line) > 16384:
                    raise ValueError('mission_process_sample_limit')
                sample = json.loads(line, object_pairs_hook=_Pairs_Require)
                _result, records = runner.Sample_Step(sample)
                events.extend(records)
        trace = {'schema_id': 'silverstar.mission-trace/1', 'profile_sha256': profile['sha256'],
                 'session_id': args.session, 'source': 'desktop_reference', 'events': events}
        MissionTrace_Write(args.output, trace, profile)
        complete = runner.index + 1 == len(profile['process']['stages'])
        print(json.dumps({'source': 'desktop_reference', 'hardware_actions': 0,
                          'stages_entered': runner.index + 1, 'complete': complete, 'trace': str(args.output)}, ensure_ascii=True))
        return 0 if complete else 3
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(MissionProcess_Main())
