"""Generate separate sensor validation projects through normal SCG entry points."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
WORK=ROOT/'.work/release-20261103/sensors'
SCG=ROOT/'apps/SCG'
sys.path[:0]=[str(SCG/'src'),str(SCG/'tools/validation')]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.validation import Project_Validate
from h743_static_validate import Scenario_Create

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fixture():
    original=ROOT/'.work/h7_20261025/verified_release/CubeMX_StaticInput'
    new=WORK/'synced-h743-fixture-v2'
    if new.exists():return new
    before={p.relative_to(original).as_posix():digest(p) for p in original.rglob('*') if p.is_file()}
    shutil.copytree(original,new)
    ioc=next(new.glob('*.ioc'));s=ioc.read_text(encoding='utf8')
    assert 'Mcu.PinsNb=34' in s and 'PE2.' not in s and 'PE3.' not in s
    s=s.replace('Mcu.PinsNb=34','Mcu.Pin34=PE2\nMcu.Pin35=PE3\nMcu.PinsNb=36')
    labels=('BMI088_A_INT2_SYNC_READY','BMI088_G_INT3_A_INT1_SYNC_NET')
    for k,label in zip((2,3),labels):
        s+=f'\nPE{k}.GPIOParameters=GPIO_Label,GPIO_ModeDefaultEXTI\nPE{k}.GPIO_Label={label}\nPE{k}.GPIO_ModeDefaultEXTI=GPIO_MODE_IT_RISING\nPE{k}.Signal=GPXTI{k}\nSH.GPXTI{k}.0=GPIO_EXTI{k}\nSH.GPXTI{k}.ConfNb=1\nNVIC.EXTI{k}_IRQn=true\\:5\\:0\\:false\\:false\\:true\\:true\\:true\\:true\n'
    ioc.write_text(s,encoding='utf8')
    p=new/'Core/Inc/main.h';s=p.read_text(encoding='utf8');marker='/* USER CODE BEGIN Private defines */'
    assert marker in s
    p.write_text(s.replace(marker,marker+'\n'+'\n'.join(f'#define {label}_Pin GPIO_PIN_{k}\n#define {label}_GPIO_Port GPIOE\n#define {label}_EXTI_IRQn EXTI{k}_IRQn' for k,label in zip((2,3),labels))),encoding='utf8')
    p=new/'Core/Src/gpio.c';s=p.read_text(encoding='utf8');marker='  /* EXTI interrupt init*/'; assert marker in s
    p.write_text(s.replace(marker,'''  __HAL_RCC_GPIOE_CLK_ENABLE();
  GPIO_InitStruct.Pin = BMI088_A_INT2_SYNC_READY_Pin | BMI088_G_INT3_A_INT1_SYNC_NET_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);
  HAL_NVIC_SetPriority(EXTI2_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI2_IRQn);
  HAL_NVIC_SetPriority(EXTI3_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI3_IRQn);
'''+marker),encoding='utf8')
    p=new/'Core/Src/sensor_fixture_irq.c';p.write_text('#include "main.h"\n' +'\n'.join(f'void EXTI{k}_IRQHandler(void)\n{{ HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_{k}); }}\n' for k in (2,3)),encoding='utf8')
    after={p.relative_to(new).as_posix():digest(p) for p in new.rglob('*') if p.is_file()}
    receipt={'original':str(original),'software_fixture':str(new),'original_sha256':before,
             'changed':{k:after[k] for k in after if after[k]!=before.get(k)},
             'original_preserved':all(digest(original/k)==v for k,v in before.items()),
             'scope':'Isolated software-only additional EXTI2/3 wiring. Physical interconnection not verified.'}
    (HERE/'h743-fixture-v2.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return new

if __name__=='__main__':
    name,version=sys.argv[1:3];service=FccgService(SCG)
    if name=='h743':
        model,_=Scenario_Create(service,fixture(),'eskf20',1,{})
        model.device_instances=[replace(item,interface='i2c',profile='bosch_sync_400_hz') if item.instance_id=='imu0' else item for item in model.device_instances]
        model.base_components.append('silverstar.installation.mag_rotation')
        model.resource_assignments.update({'imu0:drdy':'BMI088_A_INT2_SYNC_READY','imu0:auxiliary_drdy':'BMI088_G_INT3_A_INT1_SYNC_NET'})
        model=service.ProjectConfiguration_Reconcile(model).model
        model.resource_assignments.update({'imu0:drdy':'BMI088_A_INT2_SYNC_READY','imu0:auxiliary_drdy':'BMI088_G_INT3_A_INT1_SYNC_NET'})
    else:
        model=ReferenceProject_Create('ReleaseSensor_'+name,catalog=service.catalog)
        if name=='installation':
            model.base_components.append('silverstar.installation.capture')
            model.device_instances=[replace(item,profile='jy901b_mag_capture') if item.plugin=='silverstar.device.imu.jy901b' else item for item in model.device_instances]
    LoggingProfile_Reconcile(model,service.catalog)
    validation=Project_Validate(model,service.catalog)
    assert validation.valid,repr(validation)
    dest=WORK/version/name
    saved=HERE/(version+'-'+name+'-model.json')
    saved.write_text(json.dumps(model.Dictionary_Get(),indent=2)+'\n',encoding='utf8')
    print(TargetGeneration_Apply(model,service.catalog,WorkspacePolicy(SCG),dest,TargetScope.FLIGHT),flush=True)
