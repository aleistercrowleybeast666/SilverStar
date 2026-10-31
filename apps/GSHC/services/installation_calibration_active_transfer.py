"""Bounded active transaction over the existing sole maintenance owner."""
import hashlib
from pathlib import Path
from threading import Event
from uuid import uuid4
import zlib

from services.installation_calibration_active import ActivePacket_FromCandidate, ActivePacket_Check
from services.installation_calibration_backend import InstallationOutcome, InstallationResult, InstallationCapabilities_Parse
from services.installation_calibration_protocol import Request


def _Candidate_Read(path):
    path=Path(path)
    if path.stat().st_size>16384: raise ValueError('CANDIDATE_BYTE_CAPACITY')
    return ActivePacket_FromCandidate(path.read_bytes())


def _Reply_Call(backend, request, cancel, deadline, *, sid=None, rid=None):
    reply=backend._reply(backend._request(request,cancel,deadline),request.operation,sid,rid)
    if reply.status=='ERR': raise ValueError(reply.Field('reason') or 'ACTIVE_REJECTED')
    return reply


def _Readback(backend,packet,context,cancel,deadline,*,saved):
    role='SAVED' if saved else 'ACTIVE'
    reply=_Reply_Call(backend,Request('STATUS',(context,role+':0')),cancel,deadline)
    digest=hashlib.sha256(packet).hexdigest();token='S-'+digest[:30]
    if (reply.status!='OK' or reply.Field('context')!=context or reply.Field('token')!=token
            or reply.Field('sha256')!=digest or reply.Field('length')!='228'
            or reply.Field('active')!='1' or reply.Field('valid')!='1'
            or (saved and (reply.Field('saved')!='1' or int(reply.Field('saved_generation') or '0')<=0))):
        raise ValueError('ACTIVE_SNAPSHOT_IDENTITY_OR_STATE')
    status=dict(reply.fields);body=bytearray()
    for offset in range(0,228,48):
        chunk=_Reply_Call(backend,Request('READ',(context,token,str(offset))),cancel,deadline)
        data=bytes.fromhex(chunk.Field('data') or '')
        if (chunk.status!='OK' or chunk.Field('context')!=context or chunk.Field('token')!=token
                or chunk.Field('offset')!=str(offset) or len(data)!=min(48,228-offset)
                or chunk.Field('next')!=str(offset+len(data))
                or chunk.Field('end')!=('1' if offset+len(data)==228 else '0')):
            raise ValueError('ACTIVE_READBACK_PAGE')
        body.extend(data)
    if bytes(body)!=packet: raise ValueError('ACTIVE_READBACK_MISMATCH')
    ActivePacket_Check(bytes(body))
    return status


def Active_Apply(backend,candidate_path,cancel,progress):
    if not backend.capabilities or not backend.capabilities.apply_supported:
        return InstallationOutcome(InstallationResult.ApplyDisabled,'TARGET_APPLY_UNQUALIFIED')
    backend._worker();cancel=cancel or Event()
    if backend.lease is not None: return InstallationOutcome(InstallationResult.Busy,'CLOSE_CAPTURE_BEFORE_ACTIVE_APPLY')
    if not backend.cleanup_confirmed: return InstallationOutcome(InstallationResult.Unknown,'PREVIOUS_TARGET_CLEANUP_UNCONFIRMED')
    packet=_Candidate_Read(candidate_path)
    backend.lease=backend.provider.Acquire('installation') if backend.provider else None
    if backend.lease is None: return InstallationOutcome(InstallationResult.Busy,'MAINTENANCE_OWNER_BUSY')
    backend.sid=None;deadline=backend.clock()+25
    try:
        caps=_Reply_Call(backend,Request('CAPS'),cancel,deadline)
        from services.installation_calibration_protocol import Response_Encode
        backend.capabilities=InstallationCapabilities_Parse(Response_Encode(caps)[:-2],allow_simulated=backend.allow_simulated)
        if not backend.capabilities.apply_supported: raise ValueError('TARGET_APPLY_UNQUALIFIED')
        backend.sid=uuid4().hex;backend.rid=1;backend.cleanup_confirmed=False;backend._active_transaction=True
        declaration=f'228:{zlib.crc32(packet):08X}:{hashlib.sha256(packet).hexdigest()}'
        reply=_Reply_Call(backend,Request('UPLOAD',(backend.sid,'1',declaration)),cancel,deadline,sid=backend.sid,rid=1)
        if reply.status!='OK': raise ValueError('UPLOAD_NOT_ACCEPTED')
        for offset in range(0,228,48):
            backend.rid+=1
            reply=_Reply_Call(backend,Request('PUT',(backend.sid,str(backend.rid),f'{offset}:'+packet[offset:offset+48].hex().upper())),
                cancel,deadline,sid=backend.sid,rid=backend.rid)
            if reply.status!='OK': raise ValueError('UPLOAD_CHUNK_NOT_CONFIRMED')
            progress('UPLOAD',min(offset+48,228),228)
        backend.rid+=1
        reply=_Reply_Call(backend,Request('DO',(backend.sid,str(backend.rid),'APPLY')),cancel,deadline,sid=backend.sid,rid=backend.rid)
        if reply.status!='OK' or reply.Field('valid')!='1': raise ValueError('APPLY_NOT_CONFIRMED')
        status=_Readback(backend,packet,backend.sid,cancel,deadline,saved=False)
        backend._active_packet=packet;backend.status='APPLIED_NOT_SAVED'
        return InstallationOutcome(InstallationResult.Ok,'APPLIED_READBACK_VERIFIED_NOT_SAVED',status)
    except BaseException:
        backend.status='UNKNOWN';backend.Cleanup();raise


def Active_Save(backend,cancel,progress):
    if not backend.capabilities or not backend.capabilities.save_supported:
        return InstallationOutcome(InstallationResult.ApplyDisabled,'TARGET_SAVE_UNQUALIFIED')
    backend._worker();cancel=cancel or Event();packet=getattr(backend,'_active_packet',None)
    if backend.lease is None or packet is None or backend.status!='APPLIED_NOT_SAVED':
        return InstallationOutcome(InstallationResult.Invalid,'CONFIRMED_ACTIVE_TRANSACTION_REQUIRED')
    backend.rid+=1;deadline=backend.clock()+20
    request=Request('DO',(backend.sid,str(backend.rid),'SAVE'))
    try:
        for attempt in range(100):
            reply=_Reply_Call(backend,request,cancel,deadline,sid=backend.sid,rid=backend.rid)
            if reply.status=='OK': break
            if reply.status!='PENDING': raise ValueError('SAVE_STATE')
            progress('SAVE_READBACK',attempt,100)
            if cancel.wait(.1): raise InterruptedError('SAVE_COMPLETION_UNKNOWN')
        else: raise TimeoutError('SAVE_COMPLETION_UNKNOWN')
        status=_Readback(backend,packet,backend.sid,cancel,deadline,saved=True)
        cleanup=backend.Cleanup()
        if cleanup.result is not InstallationResult.Ok:
            return InstallationOutcome(InstallationResult.Unknown,'SAVED_VERIFIED_OWNER_RELEASE_UNCONFIRMED',status)
        backend.status='SAVED_READBACK_VERIFIED'
        return InstallationOutcome(InstallationResult.Ok,'SAVED_READBACK_VERIFIED_REBOOT_NOT_CHECKED',status)
    except BaseException:
        backend.status='UNKNOWN';backend.Cleanup();raise


def Active_VerifySaved(backend,candidate_path,cancel,progress):
    backend._worker();packet=_Candidate_Read(candidate_path)
    if backend.lease is not None: return InstallationOutcome(InstallationResult.Busy,'SESSION_ACTIVE')
    backend.lease=backend.provider.Acquire('installation') if backend.provider else None
    if backend.lease is None: return InstallationOutcome(InstallationResult.Busy,'MAINTENANCE_OWNER_BUSY')
    backend.sid=None
    try:
        status=_Readback(backend,packet,'B-'+packet[84:99].hex(),cancel,backend.clock()+15,saved=True)
        loaded=status.get('loaded')=='1'
        backend.status='REBOOT_LOAD_VERIFIED' if loaded else 'SAVED_READBACK_VERIFIED'
        return InstallationOutcome(InstallationResult.Ok,'REBOOT_LOAD_VERIFIED' if loaded else 'SAVED_VERIFIED_REBOOT_NOT_OBSERVED',status)
    finally: backend._release()
