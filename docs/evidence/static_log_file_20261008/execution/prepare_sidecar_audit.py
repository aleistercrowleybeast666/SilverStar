from pathlib import Path
root=Path(__file__).resolve().parent
old=root.parent/'KF6_TF_000041_InputCheck_20261007/audit_sidecars.py'
t=old.read_text(encoding='utf-8').split('summary=json.loads')[0]
t=t.replace('root=Path(__file__).resolve().parent',"mission_id=int(sys.argv[1]); assert mission_id in [44,45]\nroot=Path(__file__).resolve().parent/f'm{mission_id}'")
t=t.replace("mission=root/'missions/000041'","mission=root.parent/'input'/f'missions/{mission_id:06}'")
t=t.replace("man['mission_id']==41","man['mission_id']==mission_id").replace("final['mission_id']==41","final['mission_id']==mission_id")
t+='''
assert identity['device_config_digest']==0xA79E2E92
save('sidecar_audit.json',dict(manifest=man,objects=objects,snapshot_identity=identity,section_links=links,final_snapshot=final))
print(json.dumps(dict(mission=mission_id,final=final,snapshot_identity=identity,crc_objects=8)))
'''
(root/'audit_sidecars.py').write_text(t,encoding='utf-8')
