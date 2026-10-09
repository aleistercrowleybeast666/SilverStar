"""Fail-closed C071 integration into fresh, default CubeMX USER CODE blocks."""
import re


def C071Main_Integrate(native_main: str, pc_interface: str, user_insert) -> str:
    if pc_interface not in ('usb_cdc', 'uart'): raise ValueError('unknown PC transport')
    source = native_main
    for marker in ('Includes','2','3','Error_Handler_Debug'):
        if source.count('/* USER CODE BEGIN '+marker+' */') != 1:
            raise ValueError('ambiguous native USER CODE block: '+marker)
    source = user_insert(source,'Includes','#include "ground_bridge.h"\n#include "silverstar_assert.h"',empty=True)
    if pc_interface == 'usb_cdc':
        source = user_insert(source,'Includes','#include "usb_device.h"',empty=False)
    for statement in ('HAL_Init();','MX_USB_PCD_Init();','MX_USART2_UART_Init();'):
        if source.count(statement) != 1: raise ValueError('unreviewed native initialization: '+statement)
    source = source.replace('HAL_Init();','if (HAL_Init() != HAL_OK) { Error_Handler(); }')
    source = source.replace('MX_USB_PCD_Init();','MX_USB_Device_Init();' if pc_interface=='usb_cdc' else '/* USB PC transport is disabled in the UART profile. */')
    if pc_interface == 'usb_cdc':
        source = source.replace('MX_USART2_UART_Init();','/* UART PC transport is disabled in the USB profile. */')
    source = user_insert(source,'2','  if (GroundBridge_Init() != GROUND_BRIDGE_OK) { Error_Handler(); }',empty=True)
    loop = re.search(r'/\* USER CODE BEGIN 3 \*/(.*?)/\* USER CODE END 3 \*/',source,re.S)
    if loop is None or loop.group(1).strip() != '}':
        raise ValueError('native scheduler owns unsupported user code')
    source = source.replace('/* USER CODE BEGIN 3 */','/* USER CODE BEGIN 3 */\n    if (GroundBridge_Process(HAL_GetTick()) != GROUND_BRIDGE_OK) { Error_Handler(); }',1)
    error = re.search(r'/\* USER CODE BEGIN Error_Handler_Debug \*/(.*?)/\* USER CODE END Error_Handler_Debug \*/',source,re.S)
    if error is None: raise ValueError('missing native fault block')
    body = re.sub(r'/\*.*?\*/','',error.group(1),flags=re.S)
    if re.sub(r'\s+','',body) != '__disable_irq();while(1){}':
        raise ValueError('native Error_Handler already owns custom code')
    source = source[:error.start()]+'''/* USER CODE BEGIN Error_Handler_Debug */
  __disable_irq();
  SilverStarAssert_Fail(SILVERSTAR_ASSERT_MODULE_SYSTEM, __FILE__,
      (uint32_t)__LINE__, SILVERSTAR_ASSERT_REASON_POSTCONDITION);
  /* USER CODE END Error_Handler_Debug */'''+source[error.end():]
    # This reviewed profile fixes USE_FULL_ASSERT disabled. No target fallback
    # assert function or preprocessing option is silently introduced.
    source,count=re.subn(r'#ifdef USE_FULL_ASSERT\n.*?\n#endif /\* USE_FULL_ASSERT \*/','',source,flags=re.S)
    if count != 1: raise ValueError('unreviewed native full-assert layout')
    return source
