"""Synthetic SSLOG data paired with an unchanged, genuinely generated decoder.

No simplified Catalog/Semantics is substituted for the supplied package.
"""
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from tests.sslog_synthetic import SyntheticSslogBuilder, START_TIMESTAMP_US
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage


def GeneratedPair_Build(decoder: Path, directory: Path, *, aggregation=2, wrong_identity=False):
    directory.mkdir(parents=True, exist_ok=True)
    original = hashlib.sha256(decoder.read_bytes()).hexdigest()
    package = DecoderProfilePackage.Load(decoder)
    with zipfile.ZipFile(decoder) as archive:
        catalog = json.loads(archive.read('record_catalog.json'))
        semantics = json.loads(archive.read('project_semantics.json'))
    parameters = {group['component']:{p['id']:p['value'] for p in group['parameters']}
                  for group in semantics['firmware_algorithm_parameters']}
    frontend = parameters['silverstar.algorithm.ins.coning2_sculling2']
    gravity = frontend['gravity_mps2']
    backend = parameters.get('silverstar.algorithm.estimator.kf6', parameters.get('silverstar.algorithm.estimator.eskf15', {}))
    p0 = [backend.get('p0_'+group+'_'+axis,1.0) for group in ('position','velocity') for axis in 'enu']
    records = {r['name']:r for r in catalog['records']}
    builder = SyntheticSslogBuilder()
    hashes = bytes.fromhex(package.record_catalog_hash_128+package.project_semantics_hash_128+package.generation_profile_hash_128)
    if wrong_identity:
        hashes = hashes[:-1]+bytes((hashes[-1]^1,))
    builder.Record_Add(0x1d, struct.pack('<HHHH',package.package_schema_major,package.package_schema_minor,0,0)+hashes+bytes(8), START_TIMESTAMP_US-4)
    def add(name, timestamp, values, flags=0):
        record = records[name]
        payload = bytearray()
        formats = {'f32':'f','f64':'d','u8':'B','u16':'H','u32':'I','u64':'Q','i32':'i','i16':'h','i8':'b'}
        for field in record['fields']:
            count = field.get('count',1)
            if field['type'] == 'pad':
                payload.extend(bytes(count)); continue
            value = values.get(field['name'],0 if count == 1 else [0]*count)
            payload.extend(struct.pack('<'+formats[field['type']]*count,*([value] if count == 1 else value)))
        assert len(payload) == record['payload_size']
        builder.Record_Add(int(record['id'],0),bytes(payload),timestamp,valid_flags=flags,record_version=record['version'])
    add('CALIBRATION_RESULT',START_TIMESTAMP_US-3,{'source_id':1,'virtual_imu_id':1,'state':4,'ready':1,'accel_scale':[1]*3,'gyro_scale':[1]*3})
    add('SYSTEM_CONFIG',START_TIMESTAMP_US-2,{'version':[0,0,0,12],'configured_imu_rate_hz':200,'mechanization_subsample_count':aggregation,'mechanization_min_sample_rate_hz':50,'mechanization_max_sample_rate_hz':500,'p0_diagonal':p0})
    add('INITIAL_STATE',START_TIMESTAMP_US-1,{'q_nb':[1,0,0,0],'barometer_origin_std_m':0.2,'p0_diagonal':p0,'origin_valid_flags':3,'gnss_origin_latitude_e7':310000000,'gnss_origin_longitude_e7':1210000000})
    add('EVENT',START_TIMESTAMP_US,{'event_id':3})
    eskf = 'silverstar.algorithm.estimator.eskf15' in parameters
    if eskf:
        diagonal = [backend['p0_'+name] for name in ('position_e','position_n','position_u','velocity_e','velocity_n','velocity_u','theta_x','theta_y','theta_z','gyro_bias_x','gyro_bias_y','gyro_bias_z','accel_bias_x','accel_bias_y','accel_bias_z')]
        identity = {'snapshot_id':0,'epoch':1,'source_id':1,'calibration_generation':1,'algorithm_id':2}
        add('ESKF15_INITIAL_STATE',START_TIMESTAMP_US,{**identity,'algorithm_revision':1,'quality_revision':3,'q_nb':[1,0,0,0],'p_diagonal':diagonal})
        upper = [diagonal[row] if row==column else 0.0 for row in range(15) for column in range(row,15)]
        for part in range(4):
            add('ESKF15_INITIAL_P_PART',START_TIMESTAMP_US,{**identity,'phase':0,'part_index':part,'part_count':4,'offset':30*part,'count':30,'values':upper[part*30:(part+1)*30]})
    for index in range(21):
        timestamp = START_TIMESTAMP_US+index*5000
        if index%8==0:
            # Explicit synthetic no-fix native evidence; not a fabricated GNSS update.
            add('GNSS_NATIVE',timestamp,{'source_descriptor_id':2,'instance_id':1,'sequence':index+1,'sample_timestamp_us':timestamp,'receive_timestamp_us':timestamp,'latitude_e7':310000000,'longitude_e7':1210000000,'online':1,'horizontal_accuracy_m':1,'vertical_accuracy_m':1,'speed_accuracy_mps':1})
        add('IMU_CORRECTED',timestamp,{'sample_timestamp_us':timestamp,'receive_timestamp_us':timestamp,'sequence':index+1,'source_id':1,'virtual_imu_id':1,'valid_mask':3,'correction_valid':1,'accel_b_mps2':[0,0,gravity],'gyro_b_radps':[0,0,0]},3)
        if eskf and index and index%2==0:
            add('ESKF15_BODY_INPUT',timestamp,{'interval_start_timestamp_us':timestamp-10000,'interval_end_timestamp_us':timestamp,'sequence':index//2,'source_id':1,'calibration_generation':1,'dt_s':0.01,'body_accel_mps2':[0,0,gravity]*2,'body_gyro_radps':[0]*6})
    log = builder.File_Write(directory/'SYNTHETIC_GENERATED_DECODER.BIN')
    assert hashlib.sha256(decoder.read_bytes()).hexdigest() == original
    return log, package
