"""Explicit private source-profile config; no broad missing-macro defaults."""
import hashlib
import difflib
import re
from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX


def NativeUsbConfig_FilesRender(files, owners):
    expected=owners['usbd_conf.c'].removesuffix('.c')+'.h'
    paths=[p for p in files if p.rsplit('/',1)[-1]=='usbd_conf.h']
    if paths!=[expected]:raise ValueError('Native explicit USB config needs one header beside its LL owner')
    path=paths[0];original=files[path]
    if hashlib.sha256(original).hexdigest()!='99dcff1bcbf4fbda59073bbc32ec34c61fbf7cbc0456c4f42b568078dee56fdf':
        raise ValueError('Native explicit USB configuration needs reviewed header source profile')
    source=original.decode('utf-8-sig')
    for name in ('USBD_CLASS_BOS_ENABLED','USBD_USER_REGISTER_CALLBACK'):
        if re.search(r'(?m)^\s*#\s*(?:define|undef)\s+'+name+r'\b',source):
            raise ValueError('Native explicit USB option has an existing owner: '+name)
    anchor='#define USBD_LPM_ENABLED     0U'
    if source.count(anchor)!=1:raise ValueError('Native USB configuration anchor changed')
    source=source.replace(anchor,anchor+'''
/* Private single-FS-CDC contract: no class BOS facility or user callback registry.
 * Both choices are explicit and compiled under the unchanged -Wundef policy. */
#define USBD_CLASS_BOS_ENABLED 0U
#define USBD_USER_REGISTER_CALLBACK 0U
''',1)
    target='HardwareGenerated/ReviewedNativeConfig/'+path;derived=source.encode()
    patch=target+'.patch'
    rendered={target:derived,patch:''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),
        source.splitlines(keepends=True),fromfile=NATIVE_PREFIX+path,tofile=NATIVE_PREFIX+path)).encode()}
    manifest={'original':NATIVE_PREFIX+path,'original_sha256':hashlib.sha256(original).hexdigest(),
        'derived':target,'derived_sha256':hashlib.sha256(derived).hexdigest(),
        'patch':patch,'patch_sha256':hashlib.sha256(rendered[patch]).hexdigest(),
        'explicit_options':{'USBD_CLASS_BOS_ENABLED':0,'USBD_USER_REGISTER_CALLBACK':0},
        'scope':'Recognized native header profile only; retain static allocator and fixed native class callbacks'}
    return rendered,target.rsplit('/',1)[0],manifest
