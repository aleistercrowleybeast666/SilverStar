from pathlib import Path
p=Path('D:/python_software/SilverStar/.work/ccdi/apps/SCG/src/silverstar_fccg/generator/native_ground.py')
s=p.read_text(encoding='utf-8')
anchor="    if indexed:\n        marker='  result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);'"
replacement="""    if indexed:
        source = _Function_Replace(source,'CDC_TransmitCplt_FS','''static int8_t CDC_TransmitCplt_FS(uint8_t *Buf, uint32_t *Len, uint8_t epnum)
{
  (void)Buf; (void)Len; (void)epnum;
  return (int8_t)USBD_OK;
}''')
        marker='  result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);'"""
assert s.count(anchor)==1;s=s.replace(anchor,replacement,1)
p.write_text(s,encoding='utf-8',newline='\n')
print('Recognized empty completion hook returns explicit int8_t status; no control/EP0 hook modified')
