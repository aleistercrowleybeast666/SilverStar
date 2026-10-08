from pathlib import Path
import struct,zlib,json,hashlib,datetime,sys
mission_id=int(sys.argv[1]); assert mission_id in [44,45]
root=Path(__file__).resolve().parent/f'm{mission_id}'
mission=root.parent/'input'/f'missions/{mission_id:06}'
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def fnv(b):
    h=0x811c9dc5
    for x in b: h=((h^x)*0x01000193)&0xffffffff
    return h
def save(name,v): (root/name).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
manifest=(mission/'manifest').read_bytes()
man={'magic':manifest[:4].decode(),'schema':manifest[4],'firmware_version':list(manifest[5:8]),'mission_id':u32(manifest,8),'profile_id':u32(manifest,12),'crc_expected':u32(manifest,16),'crc_actual':zlib.crc32(manifest[:16])&0xffffffff}
assert len(manifest)==20 and man['magic']=='SSMF' and man['schema']==1 and man['mission_id']==mission_id and man['profile_id']==12 and man['crc_expected']==man['crc_actual']
objects=[]; payloads=[]
for i in range(8):
    p=mission/f'snap{i:02}.0'; b=p.read_bytes(); length=struct.unpack_from('<H',b,12)[0]; crc=zlib.crc32(b[:14]+b[18:])&0xffffffff
    assert b[:4]==b'SSOB' and b[4:8]==bytes([1,4,i,0]) and u32(b,8)>0 and length==len(b)-18 and crc==u32(b,14)
    payload=b[18:]; assert payload[:6]==b'SSMS'+bytes([2,i]) and payload[7]==0
    payloads.append(payload)
    objects.append({'file':p.name,'generation':u32(b,8),'payload_bytes':length,'section':i,'count':payload[6],'crc_expected':u32(b,14),'crc_actual':crc,'crc_valid':True,'payload_fnv1a32':fnv(payload)})
h=payloads[0]
identity={'base_instance':h[8],'mission_id':u32(h,9),'snapshot_sequence':u32(h,13),'profile_id':u32(h,17),'device_config_digest':u32(h,21),'firmware_version':list(h[25:29]),'build_tag':h[29:37].decode(),'guidance_plan_present':h[37],'imu_rate_hz':u32(h,38),'mechanization_subsample_count':struct.unpack_from('<H',h,42)[0],'expected_ins_rate_hz':u32(h,44),'imu_source_instance':h[48],'gnss_source_instance':h[49],'imu_calibration_generation':u32(h,50),'imu_correction_hash':u32(h,54),'mag_calibration_generation':u32(h,58),'mag_calibration_set_hash':u32(h,62)}
assert len(h)==172
links=[]
for i in range(6):
    generation,hashval=struct.unpack_from('<II',h,len(h)-48+i*8)
    assert generation==objects[i+1]['generation'] and hashval==objects[i+1]['payload_fnv1a32']
    links.append({'section':i+1,'generation':generation,'payload_fnv1a32':hashval,'match':True})
critical=json.loads((root/'critical_records.json').read_text(encoding='utf-8'))
snap_record=critical['MISSION_SNAPSHOT_IDENTITY'][0]['payload']
for k in ['mission_id','snapshot_sequence','base_instance','imu_calibration_generation','mag_calibration_set_hash']: assert identity[k]==snap_record[k]
assert objects[0]['generation']==snap_record['commit_generation']==1 and snap_record['ready']==1
sysconfig=critical['SYSTEM_CONFIG'][-1]['payload']
for k in ['profile_id','device_config_digest','configured_imu_rate_hz','mechanization_subsample_count','expected_ins_rate_hz']:
    sk={'configured_imu_rate_hz':'imu_rate_hz'}.get(k,k)
    assert identity[sk]==sysconfig[k]
assert identity['firmware_version']==sysconfig['version'] and identity['mission_id']==man['mission_id']
cal=payloads[6]; recordedcal=critical['CALIBRATION_RESULT'][0]['payload']; a=struct.unpack_from('<12f',cal,14)
for axis in range(3):
    for j,k in enumerate(['accel_bias_mps2','accel_scale','gyro_bias_radps','gyro_scale']): assert a[axis*4+j]==recordedcal[k][axis]
assert fnv(cal[:62])==identity['imu_correction_hash'] and u32(cal,8)==identity['imu_calibration_generation'] and cal[13]==1
p=payloads[7]
final={'mission_id':u32(p,8),'timestamp_us':struct.unpack_from('<Q',p,12)[0],'lifecycle':p[20],'recovery_valid':p[21],'landing_detected':p[22],'deploy_triggered':p[23],'deploy_completed':p[24],'logger_fault':p[25],'storage_valid':p[26],'storage_unhealthy_or_unmounted':p[27],'start_blocking_mask':u32(p,28),'warning_mask':u32(p,32),'health_sequence':u32(p,36),'deploy_action_result':u32(p,40),'landing_transition_result':u32(p,44)}
assert len(p)==48 and final['mission_id']==mission_id and final['lifecycle']==6 and final['landing_detected']==1 and final['logger_fault']==0 and final['storage_unhealthy_or_unmounted']==0

assert identity['device_config_digest']==0xA79E2E92
save('sidecar_audit.json',dict(manifest=man,objects=objects,snapshot_identity=identity,section_links=links,final_snapshot=final))
print(json.dumps(dict(mission=mission_id,final=final,snapshot_identity=identity,crc_objects=8)))
