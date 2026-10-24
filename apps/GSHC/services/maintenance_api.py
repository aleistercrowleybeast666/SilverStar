"""Bounded one-shot local maintenance API; shared clients/jobs, no GUI dependency."""
from dataclasses import asdict, dataclass
from enum import Enum
from threading import Event

from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError
from services.file_service_jobs import DeadlineCancel, LogExportJob
from transport.file_service_backend import FileServiceSerialTransport
from transport.serial_options import SerialBaud_Parse


class MaintenanceResult(str,Enum):
    Ok='ok'
    InvalidRequest='invalid_request'
    MaintenanceRequired='maintenance_required'
    Unsupported='unsupported'
    Busy='busy'
    Stale='stale'
    BadResponse='bad_response'
    Timeout='timeout'
    Cancelled='cancelled'
    IoError='io_error'
    ReleaseFailed='release_failed'


@dataclass(frozen=True)
class MaintenanceRequest:
    operation: str
    port: str
    baud: int=230400
    destination: str|None=None
    file_ids: tuple|None=None
    enter_maintenance: bool=False
    timeout: float=300


def Maintenance_Execute(request,*,cancel=None,progress=lambda *_:None,_transport_factory=FileServiceSerialTransport):
    """Return one JSON-compatible result. A failed close always prevents success."""
    output={'format':'silverstar.maintenance-result','version':1,'result':MaintenanceResult.InvalidRequest.value,
        'detail':'','operation':getattr(request,'operation','unknown'),'capabilities':None,'status':None,
        'export':None,'output':'','maintenance_enter_attempted':False,'remote_delete_requested':False,
        'source_logs_preserved':True,'release':'not_opened'}
    transport=None;client=None;job=None
    try:
        if type(request) is not MaintenanceRequest or request.operation not in ('probe','status','list','download'):
            raise ValueError('Unknown maintenance request')
        if type(request.port) is not str or not request.port.strip() or type(request.baud) is not int or SerialBaud_Parse(str(request.baud))==0:
            raise ValueError('Explicit maintenance port and valid baud required')
        if cancel is not None and not isinstance(cancel,Event):
            raise TypeError('Cancellation must be a threading.Event')
        if not callable(progress):raise TypeError('Progress must be callable')
        bounded=DeadlineCancel(cancel if cancel is not None else Event(),request.timeout)
        if request.operation in ('list','download'):
            job=LogExportJob(request.destination,file_ids=request.file_ids,list_only=request.operation=='list',
                maintenance_authorized=request.enter_maintenance,timeout=request.timeout)
            if not request.enter_maintenance:
                output.update(result=MaintenanceResult.MaintenanceRequired.value,
                    detail='Explicit enter_maintenance=true required: stops logging and blocks START until reboot')
                return output
        elif request.destination is not None or request.file_ids is not None or request.enter_maintenance:
            raise ValueError('Discovery/status cannot request a file job or ENTER')
        if bounded.is_set():raise ExportCancelled('Cancelled before opening maintenance port')
        transport=_transport_factory(request.port,request.baud)
        # File jobs own their renewable activity/transaction budget. Do not
        # nest the old absolute probe deadline around that long transfer.
        client=FileServiceClient(transport,cancel=(cancel if cancel is not None else Event())
            if job is not None else bounded)
        if request.operation=='probe':output['capabilities']=client.negotiate()
        elif request.operation=='status':
            output['status']=asdict(client.status());output['capabilities']=client.capabilities
        else:
            output['export']=asdict(job.run(client,progress=progress))
            output['capabilities']=client.capabilities
            output['output']=str(job.output or '')
        output['result']=MaintenanceResult.Ok.value
    except KeyboardInterrupt:
        output.update(result=MaintenanceResult.Cancelled.value,detail='Interrupted; remote sources retained')
    except ExportCancelled as exc:output.update(result=MaintenanceResult.Cancelled.value,detail=str(exc))
    except TimeoutError as exc:output.update(result=MaintenanceResult.Timeout.value,detail=str(exc))
    except FileServiceError as exc:
        output.update(result=exc.result.value.lower(),detail=str(exc))
    except (ValueError,TypeError) as exc:output.update(result=MaintenanceResult.InvalidRequest.value,detail=str(exc))
    except (OSError,RuntimeError,UnicodeError) as exc:output.update(result=MaintenanceResult.IoError.value,detail=str(exc))
    finally:
        if job:
            output['maintenance_enter_attempted']=job.enter_attempted
            output['output']=str(job.output or '')
            output['verified_files']=list(job.files)
            if job.enter_attempted and client is not None:
                client.cancel_remote()
                output['cancel_cleanup_error']=client.last_cancel_error
                if client.last_cancel_error and output['result']==MaintenanceResult.Ok.value:
                    output.update(result=MaintenanceResult.IoError.value,detail='Remote mailbox cancellation failed: '+client.last_cancel_error)
        if transport is not None:
            output['link_synchronization']=getattr(transport,'startup_diagnostics',None)
            try:transport.close();output['release']='closed'
            except (OSError,RuntimeError,ValueError) as exc:output.update(result=MaintenanceResult.ReleaseFailed.value,release='failed',detail=str(exc))
    return output
