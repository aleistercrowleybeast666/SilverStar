"""Verify bounded C071 native USER CODE integration and fail-closed ownership."""
from pathlib import Path
import argparse,sys
from c071_main_integrate import C071Main_Integrate

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('native',type=Path)
args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from silverstar_fccg.generator.multi_target import _UserSection_Insert
source=(args.native/'Core/Src/main.c').read_text(encoding='utf-8')
for mode in ('usb_cdc','uart'):
    result=C071Main_Integrate(source,mode,_UserSection_Insert)
    assert result.count('GroundBridge_Process(HAL_GetTick())')==1
    assert 'SilverStarAssert_Fail' in result and '#ifdef USE_FULL_ASSERT' not in result
    assert result.count('while (1)')==1
    assert ('MX_USART2_UART_Init();' in result)==(mode=='uart')
    assert ('MX_USB_Device_Init();' in result)==(mode=='usb_cdc')
for name,mutant in (
    ('owned-includes',source.replace('/* USER CODE BEGIN Includes */','/* USER CODE BEGIN Includes */\n#include "owned.h"')),
    ('owned-init',source.replace('/* USER CODE BEGIN 2 */','/* USER CODE BEGIN 2 */\nOwned_Init();')),
    ('owned-loop',source.replace('/* USER CODE BEGIN 3 */','/* USER CODE BEGIN 3 */\nOwned_Run();')),
    ('owned-fault',source.replace('__disable_irq();','Owned_Fault();\n__disable_irq();')),
    ('duplicate-native-init',source.replace('HAL_Init();','HAL_Init();\nHAL_Init();')),
    ('missing-marker',source.replace('/* USER CODE BEGIN 3 */','/* missing */')),
):
    try:C071Main_Integrate(mutant,'usb_cdc',_UserSection_Insert)
    except ValueError:print('PASS native integration rejects',name)
    else:raise AssertionError('unsafe native ownership accepted: '+name)
print('PASS both PC modes, one unchanged native scheduler loop, reused fault entry, six ownership negatives')
