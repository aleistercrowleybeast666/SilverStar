from pathlib import Path
root=Path('D:/python_software/SilverStar/.work/ccdi')
p=root/'apps/SCG/src/silverstar_fccg/generator/native_ground.py'
s=p.read_text(encoding='utf-8')
old="""        text=files[test_path].decode()
        text=text.replace('    hUsbDeviceFS.pClassData = &s_class;',
            '    hUsbDeviceFS.pClassData = &s_class;\\n    hUsbDeviceFS.pClassDataCmsit[0] = &s_class;')
        files[test_path]=text.encode()
"""
new="""        # Model the actual single-class ABI in every already-ready Host case,
        # including reset/reconnect transitions; retain all test expectations.
        for name,count in (('usb_cdc.c',3),('usb_session.c',1),('ground_backpressure.c',1)):
            path='Tests/Host/'+name
            text,actual=re.subn(r'hUsbDeviceFS\\.pClassData\\s*=\\s*([^;]+);',
                lambda match:match[0]+' hUsbDeviceFS.pClassDataCmsit[0] = '+match[1]+';',files[path].decode())
            if actual!=count:raise ValueError('Native indexed Host ABI fixture changed: '+name)
            files[path]=text.encode()
"""
assert s.count(old)==1;s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
p=root/'apps/SCG/tests/test_native_pc.py'
s=p.read_text(encoding='utf-8')
s=s.replace('def test_publication_requires_fresh_unmasked_clock_progress(tmp_path, scenario):',
    "@pytest.mark.parametrize('indexed',[False,True])\ndef test_publication_requires_fresh_unmasked_clock_progress(tmp_path, scenario, indexed):",1)
s=s.replace("    (tmp_path/'usbd_conf.h').write_text", "    if indexed:\n        path=tmp_path/'usb_device.h'\n        path.write_text(path.read_text().replace('void *pClassData;', 'void *pClassData; void *pClassDataCmsit[1]; uint8_t classId;'))\n    (tmp_path/'usbd_conf.h').write_text",1)
s=s.replace("uint8_t NativeRuntime_ReadyGet(void);\\n')", "uint8_t NativeRuntime_ReadyGet(void);\\nvoid NativeRuntime_TransportFaultRecord(void);\\n')",1)
s=s.replace('NativePcAdapter_Render(indexed=False)', 'NativePcAdapter_Render(indexed=indexed)',1)
s=s.replace('uint8_t NativeRuntime_ReadyGet(void) { return ready; }',
    'uint8_t NativeRuntime_ReadyGet(void) { return ready; }\nvoid NativeRuntime_TransportFaultRecord(void) { assert(0); }',1)
anchor="    api = Path(__file__).resolve().parents[1]"
s=s.replace(anchor,"    if indexed:\n        path=tmp_path/'test.c'\n        path.write_text(path.read_text().replace('hUsbDeviceFS.pClassData=&cls;', 'hUsbDeviceFS.pClassData=&cls;hUsbDeviceFS.pClassDataCmsit[0]=&cls;'))\n"+anchor,1)
p.write_text(s,encoding='utf-8',newline='\n')
print('Updated generated Host ABI fixtures and both publication adapter regressions; checks unchanged')
