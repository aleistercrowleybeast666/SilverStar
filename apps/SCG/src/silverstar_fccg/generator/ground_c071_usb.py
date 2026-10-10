"""Registered exact C071 mini USB integration, preserving native silicon ownership."""
import re


def C071Main_Integrate(native_main: str, pc_interface: str, user_insert) -> str:
    if pc_interface != 'usb_cdc': raise ValueError('registered C071 profile requires USB CDC')
    source = native_main.replace('\r\n', '\n')
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


def _Function_Replace(source: str, name: str, replacement: str) -> str:
    matches = list(re.finditer(r'(?m)^[\w *]+\b' + re.escape(name) + r'\([^;]*?\)\s*\{', source))
    if len(matches) != 1:
        raise ValueError('unreviewed C071 function ownership: ' + name)
    start = matches[0].start()
    end = matches[0].end()
    depth = 1
    while depth and end < len(source):
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    if depth:
        raise ValueError('unclosed C071 function: ' + name)
    return source[:start] + replacement + source[end:]


def C071Files_Integrate(files, component, user_insert, usb_conf_integrate):
    from silverstar_fccg.hardware.c071_mini import C071Companion_Validate, PREFIX
    C071Companion_Validate(component)
    for name in ('native-profile.json', 'companion-manifest.json'):
        files['Generated/C071/' + name] = (component.manifest_path.parent / name).read_bytes()
    for path in component.PayloadFiles_Get():
        relative = path.relative_to(component.payload_root).as_posix()
        if relative in files and files[relative] != path.read_bytes():
            raise ValueError('C071 companion payload collision: ' + relative)
        files[relative] = path.read_bytes()
    native = 'HardwareGenerated/STM32CubeMX/Core/Src/'
    owned = 'Platform/STM32C0/Src/'
    # Frozen native and vendor files remain intact. The control policy compiles
    # through Platform with strict/analyzer/Power10 coverage; tracked ST
    # class/core/ioreq call-site patches retain third-party provenance.
    files[owned + 'main.c'] = C071Main_Integrate(
        files[native + 'main.c'].decode('utf-8-sig'), 'usb_cdc', user_insert).encode()
    msp = files[native + 'stm32c0xx_hal_msp.c'].decode('utf-8-sig')
    marker = '__HAL_RCC_PWR_CLK_ENABLE();'
    if msp.count(marker) != 1:
        raise ValueError('unreviewed C071 remap initialization')
    files[owned + 'stm32c0xx_hal_msp.c'] = msp.replace(marker, marker +
        '\n  HAL_SYSCFG_DisableRemap(SYSCFG_REMAP_PA11 | SYSCFG_REMAP_PA12);').encode()
    conf = usb_conf_integrate(files[PREFIX + 'USB_Device/Target/usbd_conf.c']).decode().replace('\r\n', '\n')
    pattern = r'#if \(USE_HAL_PCD_REGISTER_CALLBACKS == 1U\)\n(.*?)#endif /\* USE_HAL_PCD_REGISTER_CALLBACKS \*/'
    def active(match):
        pieces = match[1].split('#else\n')
        return pieces[1] if len(pieces) == 2 else ''
    conf, count = re.subn(pattern, active, conf, flags=re.S)
    if count != 12:
        raise ValueError('unreviewed C071 callback registration branches')
    conf = conf.replace('PCD_HandleTypeDef hpcd_USB_DRD_FS;', '#include "usb.h"')
    for name in ('HAL_PCD_MspInit', 'HAL_PCD_MspDeInit'):
        conf = _Function_Replace(conf, name, '')
    conf = _Function_Replace(conf, 'USBD_LL_Init', '''USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
  uint32_t mask;
  if (pdev == NULL) { return USBD_FAIL; }
  mask = __get_PRIMASK();
  __disable_irq();
  hpcd_USB_DRD_FS.pData = pdev;
  pdev->pData = &hpcd_USB_DRD_FS;
  MX_USB_PCD_Init(); /* Native usb.c owns HAL init, clock, MSP and IRQ. */
  /* Eight descriptor pairs occupy [0,0x40); all data regions are aligned. */
  if ((HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x00, PCD_SNG_BUF, 0x40) != HAL_OK) ||
      (HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x80, PCD_SNG_BUF, 0x80) != HAL_OK) ||
      (HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, CDC_IN_EP, PCD_SNG_BUF, 0xC0) != HAL_OK) ||
      (HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, CDC_OUT_EP, PCD_SNG_BUF, 0x100) != HAL_OK) ||
      (HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, CDC_CMD_EP, PCD_SNG_BUF, 0x140) != HAL_OK))
  {
    HAL_NVIC_DisableIRQ(USB_DRD_FS_IRQn);
    if (HAL_PCD_DeInit(&hpcd_USB_DRD_FS) != HAL_OK)
    { __set_PRIMASK(mask); return USBD_FAIL; }
    hpcd_USB_DRD_FS.pData = NULL;
    pdev->pData = NULL;
    __set_PRIMASK(mask);
    return USBD_FAIL;
  }
  __set_PRIMASK(mask);
  return USBD_OK;
}''')
    conf = conf.replace('#include "usb.h"', '#include "usb.h"\n#include "pc_c071_usb.h"')
    for name, notify in (('USBD_LL_PrepareReceive', 'PcC071Usb_RxArmResult'),
                         ('USBD_LL_Transmit', 'PcC071Usb_TxStartResult')):
        match = re.search(r'(?m)^USBD_StatusTypeDef ' + name + r'\([^;]*?\)\s*\{', conf)
        if match is None:
            raise ValueError('unreviewed C071 low-level result hook: ' + name)
        end = conf.index('\n}', match.end())
        body = conf[match.start():end]
        if body.count('return usb_status;') != 1:
            raise ValueError('unreviewed C071 low-level status handling')
        endpoint = 'CDC_OUT_EP' if name == 'USBD_LL_PrepareReceive' else 'CDC_IN_EP'
        body = body.replace('return usb_status;', 'if ((ep_addr & 0x7FU) == (' + endpoint +
            ' & 0x7FU)) { ' + notify + '((usb_status == USBD_OK) ? 1U : 0U); }\n  return usb_status;')
        conf = conf[:match.start()] + body + conf[end:]
    # One static class instance, bounded allocation; a second allocation is an
    # ordinary failure. Free accepts only the actual owned allocation.
    conf = conf.replace('/* USER CODE BEGIN PV */', '''static uint32_t s_class_memory[(sizeof(USBD_CDC_HandleTypeDef)/4U)+1U];
static uint8_t s_class_allocated;
/* USER CODE BEGIN PV */''', 1)
    conf = _Function_Replace(conf, 'USBD_static_malloc', '''void *USBD_static_malloc(uint32_t size)
{
  if ((size == 0U) || (size > sizeof(s_class_memory)) || (s_class_allocated != 0U))
  { return NULL; }
  s_class_allocated = 1U;
  return s_class_memory;
}''')
    conf = _Function_Replace(conf, 'USBD_static_free', '''void USBD_static_free(void *p)
{
  if (p == s_class_memory) { s_class_allocated = 0U; }
}''')
    files[owned + 'usbd_conf.c'] = conf.encode()
    header = files[PREFIX + 'USB_Device/Target/usbd_conf.h'].decode()
    header, count = re.subn(r'(?m)^#define USBD_SELF_POWERED\s+1U\s*$',
        '#define USBD_SELF_POWERED              0U\n#define USBD_MAX_POWER                 0x32U /* 100 mA */', header)
    if count != 1:
        raise ValueError('unreviewed C071 USB power descriptor')
    files['Platform/STM32C0/Inc/usbd_conf.h'] = header.encode()
    replacements = {patch['original_path']: patch['derived_path']
                    for patch in C071Companion_Validate(component)['vendor_patches']}
    replacements.update({native + 'main.c': owned + 'main.c',
            native + 'stm32c0xx_hal_msp.c': owned + 'stm32c0xx_hal_msp.c',
            PREFIX + 'USB_Device/Target/usbd_conf.c': owned + 'usbd_conf.c',
            PREFIX + 'USB_Device/App/usbd_cdc_if.c': owned + 'usbd_cdc_if.c'})
    return replacements
