"""Host test ABI binding for the actual compiled C implementation, no model."""
import ctypes as c
import os


class Source(c.Structure):
    _fields_=[(name,c.c_uint32) for name in ("configuration","reserved_driver","reserved_model","epoch","stride","intrinsic_generation","uncertainty_us")]+[
        ("descriptor",c.c_uint16),("physical",c.c_uint16),("profile",c.c_uint16),
        ("instance",c.c_uint8),("time_basis",c.c_uint8),("axis_map",c.c_int8*3),
        ("proof_flags",c.c_uint8),("phase",c.c_uint16)]


class Snapshot(c.Structure):
    _fields_=[("sources",Source*2),("accel_bias",c.c_double*3),("accel_matrix",c.c_double*9),
        ("mag_bias",c.c_double*3),("mag_matrix",c.c_double*9),("R_GA",c.c_double*9),
        ("gyro_bias",c.c_double*3),("gyro_scale",c.c_double*3),
        ("intrinsic_id",(c.c_char*32)*2),("boot",c.c_uint8*16)]+[
        (name,c.c_uint32) for name in ("configuration","base_generation","maximum_skew_us","maximum_uncertainty_us",
            "native_health_timeout_us","source_timeout_us","face_timeout_us","selected_interval_max_us","nominal_output_millihz")]+[
        ("train_pairs",c.c_uint16),("holdout_pairs",c.c_uint16),("boot_known",c.c_uint8),
        ("R_GA_known",c.c_uint8),("offline",c.c_uint8),("reserved",c.c_uint8),
        ("gyro_known",c.c_uint8),("gyro_mode",c.c_uint8)]


class Sample(c.Structure):
    _fields_=[("sample_us",c.c_uint64),("receive_us",c.c_uint64)]+[
        (name,c.c_uint32) for name in ("sequence","epoch","uncertainty_us","flags")]+[
        ("physical",c.c_float*6),("raw",c.c_int32*6),("temperature",c.c_float)]


class Status(c.Structure):
    _fields_=[(name,c.c_uint32) for name in ("state_bytes","frozen_bytes","transaction_bytes","queue_slots","info_bytes",
        "next_pair","train_count","holdout_count","state","reason","cleanup_complete","consumer_active")]+[
        ("binding",c.c_uint8*32),("info_sha256",c.c_uint8*32)]+[
        (name,c.c_uint32) for name in ("resource_owner","resource_token","resource_generation")]


def snapshot(*,jy=False,stride=1,phase=0):
    s=Snapshot()
    for role in range(2):
        source=s.sources[role]
        source.configuration=role+1;source.epoch=0 if jy else role+1
        source.stride=stride;source.phase=phase;source.intrinsic_generation=1
        source.uncertainty_us=2**32-1 if jy else (20,30)[role]
        source.descriptor=role+1;source.physical=6 if jy else role+1
        source.profile=role+(2 if jy else 0);source.time_basis=1 if jy else 2
        source.proof_flags=0 if jy else 7
        source.axis_map[:]=(1,2,3)
        s.intrinsic_id[role].value=(b"accel-1",b"mag-1")[role]
    s.accel_matrix[:]=s.mag_matrix[:]=s.R_GA[:]=(1.,0.,0.,0.,1.,0.,0.,0.,1.)
    s.mag_bias[:]=(3.,-2.,1.)
    s.boot[:]=bytes(range(1,17));s.boot_known=1;s.offline=int(not jy)
    s.configuration=0x12345678;s.maximum_skew_us=2000;s.maximum_uncertainty_us=1000
    s.native_health_timeout_us=s.source_timeout_us=250000;s.face_timeout_us=10000000
    s.selected_interval_max_us=210000;s.nominal_output_millihz=5000
    s.train_pairs=s.holdout_pairs=3
    return s


class Library:
    def __init__(self,path=None):
        self.dll=c.CDLL(path or os.environ["INSTALLATION_CAPTURE_DLL"])
        ptr=c.POINTER;u8,u16,u32,u64=c.c_uint8,c.c_uint16,c.c_uint32,c.c_uint64
        signatures={"Enable":[u8],"Configure":[ptr(Snapshot)],"Status":[ptr(Status)],
            "InfoRead":[u16,ptr(u8),ptr(u16),ptr(u16),ptr(u8)],
            "Begin":[ptr(u8),u32,ptr(u8),u64],"Face":[ptr(u8),u32,u8,u8,u8,u16,u64],
            "SourcePush":[u8,ptr(Sample),u64],"Poll":[u64],"EventPeek":[ptr(c.c_char),u16,ptr(u16)],
            "EventCommit":[u8],"Cancel":[ptr(u8),u32,u64],"ProducerStopped":[],"Release":[],"Revoke":[],
            "Number":[c.c_double,ptr(c.c_char),ptr(u16)],"Hash":[ptr(u8),u16,ptr(u8)],"TestGuard":[u8],
            "TestReset":[],"TestCorruptQueue":[]}
        signatures.update(ResourceClaim=[u8,ptr(u32)],ResourceRelease=[u8,u32])
        signatures['RequestTouch']=[ptr(u8),u32,u64]
        for name,args in signatures.items():
            function=getattr(self.dll,"InstallationCapture_"+name);function.argtypes=args;function.restype=c.c_int
            setattr(self,name,function)
        self.sid=(u8*16).from_buffer_copy(bytes.fromhex("1"*32));self.config=None

    def configure(self,config=None):
        self.TestReset();assert self.Enable(1)==0
        self.config=config or snapshot();assert self.Configure(c.byref(self.config))==0
        return self.info()

    def status(self):
        result=Status();assert self.Status(c.byref(result))==0;return result

    def page(self,cursor):
        page=(c.c_uint8*48)();length=c.c_uint16();next_cursor=c.c_uint16();end=c.c_uint8()
        assert self.InfoRead(cursor,page,c.byref(length),c.byref(next_cursor),c.byref(end))==0
        return bytes(page[:length.value]),next_cursor.value,end.value

    def info(self):
        data=b"";cursor=0
        for _ in range(171):
            page,cursor,end=self.page(cursor);data+=page
            if end:return data
        raise AssertionError("C INFO page budget")

    def begin(self):
        binding=(c.c_uint8*15).from_buffer_copy(bytes(self.status().binding[:15]))
        assert self.Begin(self.sid,1,binding,0)==0

    def face(self,rid=2,mode=0,now=0):return self.Face(self.sid,rid,mode,1,0,1,now)

    def sample(self,role,index,t):
        sample=Sample();source=self.config.sources[role]
        sample.sequence=index;sample.epoch=source.epoch
        sample.sample_us=t+(100 if role else 0);sample.receive_us=t+300
        if source.time_basis==1:sample.sample_us=sample.receive_us
        sample.uncertainty_us=source.uncertainty_us;sample.flags=24
        sample.physical[:]=(9.80665,0.,0.,0.,0.,0.) if role==0 else (48.,2.,3.,0.,0.,0.)
        sample.raw[:]=(1,2,3,4,5,6) if role==0 else (7,8,9,0,0,0)
        sample.temperature=25.
        return sample

    def feed(self,index,t):
        return tuple(self.SourcePush(role,c.byref(self.sample(role,index,t)),t+300) for role in range(2))

    def peek(self):
        buffer=c.create_string_buffer(441);buffer[439]=b"X";buffer[440]=b"Y";length=c.c_uint16()
        result=self.EventPeek(buffer,439,c.byref(length))
        assert buffer[439:441]==b"XY"
        return result,bytes(buffer[:length.value])

    def drain(self):
        lines=[]
        for _ in range(4):
            result,line=self.peek()
            if result!=0:break
            lines.append(line);assert self.EventCommit(1)==0
        return lines
