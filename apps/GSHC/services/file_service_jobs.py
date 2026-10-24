"""Shared GUI/CLI log-copy job. No UI, port ownership, delete or implicit ENTER."""
import hashlib
import json
import os
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from config import APP_VERSION
from services.device_export import ExportCancelled
from services.transfer_progress import BatchProgress, TransferProgress
from services.file_service_client import (
    FileServiceError,
    FileServiceResult,
    validate_download_directory,
)


class DeadlineCancel:
    """Event-compatible cancellation with a bounded whole-operation deadline."""
    def __init__(self,event,seconds):
        if type(seconds) not in (int,float) or not 0<seconds<=3600:
            raise ValueError('Operation timeout must be in (0, 3600] seconds')
        self.event=event
        self.deadline=time.monotonic()+seconds

    def is_set(self):
        if time.monotonic()>=self.deadline:raise TimeoutError('Maintenance operation deadline exceeded')
        return self.event.is_set()

    def wait(self,seconds):
        self.is_set()
        result=self.event.wait(min(seconds,max(0,self.deadline-time.monotonic())))
        self.is_set()
        return result


class TransferBudgetCancel:
    """Owner-thread lease: validated activity renews idle, never transaction/total.

    A repeated PENDING may show liveness but cannot prove storage progress:
    each asynchronous request and the maintenance-ready phase have their own
    absolute bound. The entire file job additionally stops after three hours.
    """
    def __init__(self,event,seconds,*,total_seconds=10800,clock=None,sleep=None):
        if type(seconds) not in (int,float) or not 0<seconds<=3600:
            raise ValueError('Transaction timeout must be in (0, 3600] seconds')
        if type(total_seconds) not in (int,float) or not 0<total_seconds<=10800:
            raise ValueError('Transfer cap must be in (0, 10800] seconds')
        self.event,self.seconds=event,seconds
        self.clock,self.sleep=clock or time.monotonic,sleep or time.sleep
        now=self.clock()
        self.deadline=now+total_seconds
        self.idle_seconds=min(30.0,seconds)
        self.last_activity=now
        self.transaction_deadline=self.phase_deadline=None

    def is_set(self):
        if self.event.is_set():return True
        now=self.clock()
        if now>=self.deadline:raise TimeoutError('Transfer safety cap exceeded (maximum three hours)')
        if self.phase_deadline is not None and now>=self.phase_deadline:
            raise TimeoutError('Maintenance-ready phase deadline exceeded')
        if self.transaction_deadline is not None and now>=self.transaction_deadline:
            raise TimeoutError('Storage transaction deadline exceeded; repeated PENDING is not completion')
        if now-self.last_activity>=self.idle_seconds:
            raise TimeoutError('Transfer made no validated activity before inactivity deadline')
        return False

    def Activity_Record(self):
        if self.is_set():raise ExportCancelled('Maintenance operation cancelled')
        self.last_activity=self.clock()

    def Transaction_Begin(self):
        if self.is_set():raise ExportCancelled('Maintenance operation cancelled')
        if self.transaction_deadline is not None:raise RuntimeError('Overlapping storage transactions')
        self.transaction_deadline=self.clock()+self.seconds

    def Transaction_End(self):
        self.transaction_deadline=None

    def Phase_Begin(self):
        if self.is_set():raise ExportCancelled('Maintenance operation cancelled')
        if self.phase_deadline is not None:raise RuntimeError('Overlapping maintenance phases')
        self.phase_deadline=self.clock()+self.seconds

    def Phase_End(self):
        self.phase_deadline=None

    def wait(self,seconds):
        # Event.wait short sleeps are coarse on some Windows hosts. A bounded
        # high-resolution sleep slice keeps cancellation checks within 5 ms
        # of requested waiting, without changing global timer settings.
        remaining=seconds
        while remaining>0:
            if self.is_set():return True
            step=min(.005,remaining)
            self.sleep(step)
            remaining-=step
        return self.is_set()


@dataclass(frozen=True)
class LogExportReport:
    ids: tuple
    selected_ids: tuple
    output: str
    files: tuple
    manifest_sha256: str
    maintenance_enter_attempted: bool
    remote_delete_requested: bool=False


class LogExportJob:
    def __init__(self,destination=None,*,file_ids=None,list_only=False,maintenance_authorized=False,timeout=300):
        if type(list_only) is not bool or type(maintenance_authorized) is not bool:
            raise ValueError('Explicit boolean operation flags required')
        if file_ids is not None and (type(file_ids) is not tuple or not 1<=len(file_ids)<=1024 or
                len(set(file_ids))!=len(file_ids) or any(type(item) is not int or not 1<=item<=999999 for item in file_ids)):
            raise ValueError('Select 1..1024 unique mission IDs')
        if list_only and (destination is not None or file_ids is not None):
            raise ValueError('List operation accepts no destination/mission selection')
        if not list_only and destination is None:
            raise ValueError('Download requires an explicit destination directory')
        self.destination=Path(destination) if destination is not None else None
        self.file_ids,self.list_only,self.authorized,self.timeout=file_ids,list_only,maintenance_authorized,timeout
        self.output=None
        self.files=[]
        self.ids=()
        self.enter_attempted=False

    def run(self,client,*,progress=lambda *_:None,catalog=lambda _:None,destination_validated=lambda _:None,byte_progress=None):
        if not self.authorized:
            raise PermissionError('Explicit maintenance authorization required; ENTER stops logging and blocks START until reboot')
        cancel=client.cancel
        budget=TransferBudgetCancel(cancel,self.timeout)
        client.cancel=budget
        try:
            if byte_progress is not None:byte_progress(TransferProgress(0,None,'listing'))
            client._check()
            if not self.list_only:
                if self.destination is None:raise ValueError('Select an explicit destination directory')
                self.destination=validate_download_directory(self.destination)
                destination_validated(str(self.destination))
            snapshot=client.status()
            if snapshot.age_ms>3000 or snapshot.lifecycle not in (2,3,7):
                raise FileServiceError(FileServiceResult.BUSY,'Fresh PREFLIGHT/READY/POSTFLIGHT evidence required before ENTER')
            self.enter_attempted=True
            budget.Phase_Begin()
            try:client.enter_maintenance()
            finally:budget.Phase_End()
            self.ids=tuple(client.list_closed());catalog(list(self.ids))
            selected=self.ids if self.file_ids is None else self.file_ids
            if any(identifier not in self.ids for identifier in selected):
                raise FileServiceError(FileServiceResult.STALE,'Selected mission is absent from the fresh closed-log list')
            if self.list_only or not selected:
                return LogExportReport(self.ids,tuple(selected),'',(),'',True)
            self.output=self.destination/('SilverStar_download_'+time.strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:12])
            self.output.mkdir(exist_ok=False)
            batch = BatchProgress(selected,getattr(client,'catalog_sizes',{}),byte_progress or (lambda _:None))
            for identifier in selected:
                if byte_progress is None:
                    path=client.download(identifier,self.output,progress=progress)
                else:
                    path=client.download(identifier,self.output,progress=progress,
                        byte_progress=lambda done,total,stage:batch.update(identifier,done,total,stage))
                batch.send('verifying','manifest readback')
                digest=hashlib.sha256();crc=0
                with path.open('rb') as stream:
                    for data in iter(lambda:stream.read(1024*1024),b''):
                        client._check();digest.update(data);crc=zlib.crc32(data,crc)
                        budget.Activity_Record()
                token=path.stem.split('_',2)[2]
                if f'1-{crc:08X}-{path.stat().st_size:08X}'!=token:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE,'Published log changed before manifest readback')
                self.files.append({'path':path.name,'role':'flight_log','format':'SSLOG','format_version':'0.0',
                    'file_id':identifier,'size_bytes':path.stat().st_size,'sha256':digest.hexdigest(),'crc32':f'{crc:08X}',
                    'source_token':token,'integrity':'chunk_crc32+whole_crc32+meta_recheck+local_readback'})
                batch.completed += path.stat().st_size
                batch.received = batch.completed
            manifest={'schema_version':1,'format':'silverstar.session-export','session_id':self.output.name,
                'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_app':{'name':'GSHC','version':APP_VERSION},
                'protocols':{'log_file_service':1,'sslog':'0.0'},'files':self.files,
                'remote_delete_requested':False,'resume_allowed':False,
                'recorded_descriptor_included':False,'decoder_package_included':False}
            encoded=json.dumps(manifest,indent=2).encode('utf-8')
            path=self.output/'manifest.json'
            with path.open('xb') as stream:
                if stream.write(encoded)!=len(encoded):raise OSError('Incomplete manifest write')
                stream.flush();os.fsync(stream.fileno())
            if path.read_bytes()!=encoded:raise OSError('Manifest readback mismatch')
            client._check()
            batch.send('verified','manifest readback')
            return LogExportReport(self.ids,tuple(selected),str(self.output),tuple(self.files),hashlib.sha256(encoded).hexdigest(),True)
        finally:
            client.cancel=cancel
