"""Shared real-class descriptor faults; no replacement parser in the harness."""

import subprocess


DESCRIPTOR_CASES = (
    "descriptor-getters-normal", "descriptor-zero-length", "descriptor-short-endpoint",
    "descriptor-trailing-invalid", "descriptor-total-over-capacity", "descriptor-truncated-tail",
    "descriptor-null-owner", "descriptor-foreign-owner", "descriptor-request-invalid",
    "descriptor-null-length",
)

DESCRIPTOR_FAULTS = r'''
static int DescriptorFault(const char *scenario)
{
 uint16_t length=0U;
 uint8_t *descriptor=USBD_CDC.GetFSConfigDescriptor(&length);
 assert(descriptor!=NULL && length==USB_CDC_CONFIG_DESC_SIZ);
 if(!strcmp(scenario,"descriptor-getters-normal"))
 {
  assert(USBD_CDC.GetHSConfigDescriptor(&length)==descriptor && length==USB_CDC_CONFIG_DESC_SIZ);
  assert(USBD_CDC.GetOtherSpeedConfigDescriptor(&length)==descriptor && length==USB_CDC_CONFIG_DESC_SIZ);
  assert(USBD_CDC.GetFSConfigDescriptor(&length)==descriptor && length==USB_CDC_CONFIG_DESC_SIZ);
  assert(USBD_GetEpDesc(descriptor,CDC_CMD_EP)!=NULL);
  assert(USBD_GetEpDesc(descriptor,CDC_IN_EP)!=NULL);
  assert(USBD_GetEpDesc(descriptor,CDC_OUT_EP)!=NULL);
  assert(USBD_GetEpDesc(descriptor,0x83U)==NULL);return 1;
 }
 if(!strcmp(scenario,"descriptor-null-length"))
 { assert(USBD_CDC.GetFSConfigDescriptor(NULL)==NULL);
   assert(USBD_CDC.GetHSConfigDescriptor(NULL)==NULL);
   assert(USBD_CDC.GetOtherSpeedConfigDescriptor(NULL)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-null-owner"))
 { assert(USBD_GetEpDesc(NULL,CDC_IN_EP)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-foreign-owner"))
 { uint8_t other[USB_CDC_CONFIG_DESC_SIZ];memcpy(other,descriptor,sizeof(other));
   assert(USBD_GetEpDesc(other,CDC_IN_EP)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-zero-length"))
 { descriptor[9]=0U;assert(USBD_GetEpDesc(descriptor,CDC_IN_EP)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-total-over-capacity"))
 { descriptor[2]=(uint8_t)(USB_CDC_CONFIG_DESC_SIZ+1U);
   assert(USBD_GetEpDesc(descriptor,CDC_CMD_EP)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-truncated-tail"))
 { descriptor[2]=(uint8_t)(USB_CDC_CONFIG_DESC_SIZ-1U);
   assert(USBD_GetEpDesc(descriptor,CDC_CMD_EP)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-short-endpoint") || !strcmp(scenario,"descriptor-trailing-invalid"))
 { uint8_t *endpoint=USBD_GetEpDesc(descriptor,CDC_IN_EP);assert(endpoint!=NULL);
   endpoint[0]=2U;assert(USBD_GetEpDesc(descriptor,
       !strcmp(scenario,"descriptor-short-endpoint")?CDC_IN_EP:CDC_CMD_EP)==NULL);return 1; }
 if(!strcmp(scenario,"descriptor-request-invalid"))
 {
  allow_control_error=1U; /* The malformed getter itself must stall before Setup. */
  uint8_t *endpoint=USBD_GetEpDesc(descriptor,CDC_IN_EP);assert(endpoint!=NULL);
  endpoint[0]=2U;uint8_t before[USB_CDC_CONFIG_DESC_SIZ];memcpy(before,descriptor,sizeof(before));
  assert(USBD_CDC.GetHSConfigDescriptor(&length)==descriptor && length==0U);
  assert(!memcmp(before,descriptor,sizeof(before)));
  assert(USBD_CDC.GetOtherSpeedConfigDescriptor(&length)==descriptor && length==0U);
  assert(!memcmp(before,descriptor,sizeof(before)));
  unsigned prior=ep0_ll_calls;
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,USB_DESC_TYPE_CONFIGURATION<<8,67U)==USBD_FAIL);
  assert(hUsbDeviceFS.ep0_state==USBD_EP0_STALL && ep0_ll_calls==prior);
  assert(!memcmp(before,descriptor,sizeof(before)));return 1;
 }
 return 0;
}
'''


def DescriptorCases_Run(program):
    rows = []
    for case in DESCRIPTOR_CASES:
        command = [str(program), case]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2)
            rows.append({"command": command, "exit": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            rows.append({"command": command, "exit": "TIMEOUT", "timeout_seconds": 2,
                         "stdout": stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout,
                         "stderr": stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr})
    return rows
