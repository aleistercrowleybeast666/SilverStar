"""Immutable full candidate snapshots and a TF-object persistence boundary.

This stores software candidates, never active calibration. Existing SSIC kind 1
magnetic records and SSLOG are untouched. The object adapter owns atomic writes;
no serial, TF device, or application operation is performed here.
"""
from enum import Enum
import hashlib
import json
from pathlib import Path
import struct
import zlib

from services.installation_calibration_capture_contract import InfoSnapshot_Decode
from services.installation_calibration_contract import InstallationContract_Load


class InstallationCandidateResult(str, Enum):
    Ok="OK"
    Invalid="INVALID"
    Stale="DEPENDENCY_CHANGED"
    StorageError="STORAGE_ERROR"
    ApplyDisabled="APPLY_DISABLED"


MAX_BYTES=16384
KIND=2  # SSIC v1 kind 1 remains the existing magnetic-intrinsic record.
HEADER=32


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode('ascii')


def _sha(data):return hashlib.sha256(data).hexdigest()


def Candidate_Encode(snapshot):
    if type(snapshot) is not dict or set(snapshot)!={"kind","binding","solution","raw_archive_sha256","validation","hardware_acceptance","apply_allowed","save_allowed"}:
        raise ValueError("COMPLETE_CANDIDATE_REQUIRED")
    if (snapshot["kind"]!="INSTALLATION_SOFTWARE_CANDIDATE" or snapshot["hardware_acceptance"]!="NOT_PROVEN"
            or snapshot["apply_allowed"] is not False or snapshot["save_allowed"] is not False):
        raise ValueError("HARDWARE_ACCEPTANCE_NOT_AUTHORIZED")
    raw_sha=snapshot['raw_archive_sha256']
    if type(raw_sha) is not str or len(raw_sha)!=64 or any(c not in '0123456789abcdef' for c in raw_sha):raise ValueError("RAW_DIGEST_REQUIRED")
    binding=_canonical(snapshot['binding'])
    if 'runtime_imu' not in snapshot['binding']:raise ValueError('COMPLETE_RUNTIME_IMU_SNAPSHOT_REQUIRED')
    InfoSnapshot_Decode(binding,InstallationContract_Load().Read()['info_snapshot'])
    from services.installation_calibration_backend import (InstallationBinding_Parse,InstallationCapabilities,
        InstallationOutcome,InstallationResult)
    plan=snapshot['binding']['face_plan']
    simulated=all(item['identity_scope']=='SYNTHETIC_ENDPOINT'
        for item in snapshot['binding']['capture_provenance']['sources'].values())
    caps=InstallationCapabilities(InstallationOutcome(InstallationResult.Ok,'LOCAL_CANDIDATE'),
        plan['train_pairs'],plan['holdout_pairs'],4096,simulated)
    InstallationBinding_Parse(binding,'B-'+snapshot['binding']['binding_digest'][:30],caps)
    solution=snapshot['solution'];validation=snapshot['validation']
    if (type(solution) is not dict or solution.get('binding_digest')!=snapshot['binding']['binding_digest']
            or solution.get('apply_allowed') is not False or solution.get('save_allowed') is not False
            or solution.get('gyro_scale_status')!='NOT_ESTIMATED_STATIC_SIX_FACE'
            or type(validation) is not dict or validation.get('result')!='PASS_SOFTWARE_HOLDOUT'
            or validation.get('selects_solution') is not False):raise ValueError("VALIDATED_FROZEN_SOLUTION_REQUIRED")
    report=solution.get('report',{})
    if report.get('result')!='CANDIDATE_ONLY' or not report.get('candidates'):raise ValueError("NO_ACCEPTED_SOFTWARE_CANDIDATE")
    from services.installation_calibration_fit import _matrix, _vec, Intrinsic, SensorIdentity
    for key in ('accel_candidate','mag_parent'):
        value=dict(solution[key]);value['identity']=SensorIdentity(**value['identity']);Intrinsic(**value)
    _vec(solution['gyro_bias']);_matrix(report['candidates'][0]['R_AM'],rotation=True)
    if (_canonical(solution['mag_parent'])!=_canonical(snapshot['binding']['mag'])
            or validation.get('context_digest')!=report.get('context_digest')
            or validation.get('solution_sha256')!=_sha(_canonical(report['candidates'][0]))):
        raise ValueError('FROZEN_DEPENDENCY_OR_SOLUTION_MISMATCH')
    body=_canonical(snapshot)
    if not 1<=len(body)<=MAX_BYTES-HEADER-8:raise ValueError("CANDIDATE_CAPACITY")
    identity=snapshot['binding']['sources']['IMU']['identity']
    header=struct.pack('<4sBBBBHHB3xIIII',b'SSIC',1,KIND,1,2,
        identity['descriptor'],identity['physical'],identity['instance'],
        snapshot['binding']['configuration_u32'],0,0,0)
    return header+struct.pack('<II',len(body),zlib.crc32(body))+body


def Candidate_Decode(packet,*,current_binding=None):
    if type(packet) is not bytes or not HEADER+8<len(packet)<=MAX_BYTES or packet[:8]!=b'SSIC'+bytes((1,KIND,1,2)):
        raise ValueError("CANDIDATE_ENVELOPE")
    length,crc=struct.unpack('<II',packet[HEADER:HEADER+8]);body=packet[HEADER+8:]
    if length!=len(body) or crc!=zlib.crc32(body):raise ValueError("CANDIDATE_CRC_OR_LENGTH")
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError("DUPLICATE_CANDIDATE_KEY")
            result[key]=value
        return result
    value=json.loads(body,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('FINITE_JSON_REQUIRED')))
    if Candidate_Encode(value)!=packet:raise ValueError("NONCANONICAL_CANDIDATE")
    if current_binding is not None and _canonical(current_binding)!=_canonical(value['binding']):
        return InstallationCandidateResult.Stale,value
    return InstallationCandidateResult.Ok,value


class InstallationCandidateStore:
    """Atomic-object interface shared by the offline TF image and future owner.

    Adapter: Read(key)->bytes|None, Create(key,bytes)->bool (exclusive immutable),
    Commit(expected_generation,bytes)->bool (atomic verified opposite slot).
    Only the adapter's confirmed readback permits a new generation publication.
    Old objects are never deleted. No real apply authorization is derived here.
    """
    def __init__(self,objects):self.objects=objects

    def Load(self,current_binding):
        try:
            manifest=self.objects.Read('head')
            if manifest is None:return InstallationCandidateResult.Invalid,None
            data=json.loads(manifest);packet=self.objects.Read(data['object'])
            if packet is None or _sha(packet)!=data['sha256']:raise ValueError('OBJECT_HASH')
            result,value=Candidate_Decode(packet,current_binding=current_binding)
            return result,{'generation':data['generation'],'candidate':value,'sha256':data['sha256']}
        except (OSError,ValueError,KeyError,TypeError):return InstallationCandidateResult.StorageError,None

    def Save(self,packet,current_binding):
        try:result,value=Candidate_Decode(packet,current_binding=current_binding)
        except (ValueError,KeyError,TypeError,struct.error):return InstallationCandidateResult.Invalid,None
        if result!=InstallationCandidateResult.Ok:return result,None
        try:
            old=self.objects.Read('head');generation=0 if old is None else json.loads(old)['generation']
            if type(generation) is not int or not 0<=generation<64:raise ValueError('OFFLINE_IMAGE_GENERATION_CAPACITY')
            sha=_sha(packet);key='candidate-'+sha
            if old is not None and json.loads(old).get('sha256')==sha:
                return self.Load(current_binding)
            existing=self.objects.Read(key)
            if existing is None:
                if not self.objects.Create(key,packet):raise OSError('OBJECT_CREATE_FAILED')
            elif existing!=packet:raise ValueError('IMMUTABLE_OBJECT_CONFLICT')
            if self.objects.Read(key)!=packet:raise OSError('OBJECT_READBACK_FAILED')
            new=_canonical({'generation':generation+1,'object':key,'sha256':sha,'kind':KIND})
            if not self.objects.Commit(generation,new):raise OSError('COMMIT_NOT_CONFIRMED')
            if self.objects.Read('head')!=new:raise OSError('COMMIT_READBACK_UNCERTAIN')
            return self.Load(current_binding)
        except (OSError,ValueError,KeyError,TypeError):return InstallationCandidateResult.StorageError,None


class OfflineTfObjects:
    """Host-directory TF-image adapter, never mounted card/device access.

    Two exclusive generation files represent the verified SSOB head slots.
    Failed/partial manifest writes cannot replace an earlier valid generation.
    This is a software fault-injection boundary, not a FAT/card power-loss proof.
    """
    def __init__(self,path):
        self.root=Path(path).resolve();self.root.mkdir(parents=True,exist_ok=True)

    def Read(self,key):
        if key=='head':
            heads=[]
            for index,path in enumerate(self.root.glob('head-*.json')):
                if index>=64:raise ValueError('HEAD_INVENTORY_CAPACITY')
                if path.is_symlink():raise ValueError('NO_HEAD_SYMLINK')
                try:
                    if path.stat().st_size>512:raise ValueError('HEAD_BYTE_CAPACITY')
                    packet=path.read_bytes();envelope=json.loads(packet)
                    body=envelope['body'].encode('ascii')
                    if _sha(body)!=envelope['sha256']:continue
                    value=json.loads(body)
                    if type(value['generation']) is int and 0<value['generation']<2**32:heads.append((value['generation'],body))
                except (OSError,ValueError,KeyError,TypeError):continue
            if not heads:
                if any(self.root.glob('head-*.json')):raise ValueError('NO_VALID_SURVIVING_HEAD')
                return None
            return max(heads,key=lambda row:row[0])[1]
        if len(key)!=74 or not key.startswith('candidate-') or any(c not in '0123456789abcdef' for c in key[10:]):raise ValueError('SAFE_OBJECT_KEY')
        path=self.root/(key+'.ssic')
        if path.is_symlink():raise ValueError('NO_OBJECT_SYMLINK')
        if path.exists() and path.stat().st_size>MAX_BYTES:raise ValueError('OBJECT_BYTE_CAPACITY')
        return path.read_bytes() if path.exists() else None

    def Create(self,key,data):
        self.Read(key)  # Validate the key before constructing a destination.
        with (self.root/(key+'.ssic')).open('xb') as stream:
            if stream.write(data)!=len(data):raise OSError('SHORT_OBJECT_WRITE')
            stream.flush();__import__('os').fsync(stream.fileno())
        return True

    def Commit(self,expected_generation,data):
        old=self.Read('head');current=0 if old is None else json.loads(old)['generation']
        if current!=expected_generation:return False
        generation=json.loads(data)['generation']
        if generation!=current+1:return False
        envelope=_canonical({'body':data.decode('ascii'),'sha256':_sha(data)})
        with (self.root/f'head-{generation:010d}.json').open('xb') as stream:
            if stream.write(envelope)!=len(envelope):raise OSError('SHORT_MANIFEST_WRITE')
            stream.flush();__import__('os').fsync(stream.fileno())
        return True
