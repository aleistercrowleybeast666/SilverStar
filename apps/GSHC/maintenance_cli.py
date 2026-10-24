"""Local JSON CLI for explicit maintenance/TF operations; never starts a mission."""
import argparse
import json

from services.maintenance_api import Maintenance_Execute, MaintenanceRequest


def MaintenanceCli_Run(argv=None,*,_execute=Maintenance_Execute):
    parser=argparse.ArgumentParser(description='Bounded maintenance / TF copy API; source logs are retained')
    parser.add_argument('operation',choices=('probe','status','list','download'))
    parser.add_argument('--port',required=True,help='Explicit FC maintenance port, separate from ground telemetry')
    parser.add_argument('--baud',type=int,default=230400)
    parser.add_argument('--timeout',type=float,default=300,help='Probe/status deadline or file transaction timeout (seconds, max 3600); file jobs also enforce inactivity and a three-hour cap')
    parser.add_argument('--enter-maintenance',action='store_true',help='Explicitly allow logging closure and START exclusion until reboot')
    parser.add_argument('--destination',help='Existing explicit local directory; every operation creates a unique subdirectory')
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--mission',type=int,action='append',help='Closed mission ID; repeat for multiple selected logs')
    selection.add_argument('--all-closed',action='store_true',help='Explicitly copy every freshly listed closed log')
    args=parser.parse_args(argv)
    if args.operation=='download' and (not args.destination or not (args.mission or args.all_closed)):
        parser.error('download requires --destination and either --mission or --all-closed')
    if args.operation!='download' and (args.destination or args.mission or args.all_closed):
        parser.error('Destination/selection are only valid for download')
    request=MaintenanceRequest(args.operation,args.port,args.baud,args.destination,
        tuple(args.mission) if args.mission else None,args.enter_maintenance,args.timeout)
    result=_execute(request)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0 if result['result']=='ok' else 130 if result['result']=='cancelled' else 2


if __name__=='__main__':raise SystemExit(MaintenanceCli_Run())
