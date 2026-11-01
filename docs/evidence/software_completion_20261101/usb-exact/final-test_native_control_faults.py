"""Actual exact-profile EP0 stack faults; LL transport is a Host substitute."""
import hashlib
import json
from pathlib import Path
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

import test_usb_lifecycle_normal as normal
from test_round2_targets import _GroundBoardProject_Get


@pytest.fixture(params=('F103', 'F407'))
def exact_control(request, tmp_path, tmp_path_factory, builtin_catalog, monkeypatch):
    config = tmp_path / 'ground.ssproject'
    model = _GroundBoardProject_Get(builtin_catalog)
    model.ground_target = replace(model.ground_target, pc_interface='usb_cdc', pc_resource='',
        tx_led_resource='', rx_led_resource='', activity_led_enabled=False)
    model.air_link = replace(model.air_link, radio_family='sx128x', frequency_hz=2473000000, bandwidth_hz=800000)
    config.write_text(json.dumps(model.Dictionary_Get()), encoding='utf8')
    monkeypatch.setenv('SILVERSTAR_NATIVE_BACKEND_CONFIG', str(config))
    return normal.first_batch.__wrapped__(SimpleNamespace(param=request.param), tmp_path, tmp_path_factory, builtin_catalog)


FAULTS = r'''
static USBD_StatusTypeDef Request(uint8_t bm,uint8_t req,uint16_t value,uint16_t length)
{
 uint8_t bytes[8]={bm,req,(uint8_t)value,(uint8_t)(value>>8),0U,0U,(uint8_t)length,(uint8_t)(length>>8)};
 return USBD_LL_SetupStage(&hUsbDeviceFS,bytes);
}
static void FailureCheck(void)
{
 assert(hUsbDeviceFS.ep0_state==USBD_EP0_STALL);
 USBD_CDC_HandleTypeDef *cdc=(USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
 assert(cdc!=NULL && cdc->CmdOpCode==0xFFU && cdc->CmdLength==0U);
 unsigned before=ep0_ll_calls;
 assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,NULL)==USBD_OK);
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,NULL)==USBD_OK);
 assert(ep0_ll_calls==before && hUsbDeviceFS.ep0_state==USBD_EP0_STALL);
 assert(Request(0xA1U,CDC_GET_LINE_CODING,0U,7U)==USBD_OK);
 ControlInDone();
}
static int ControlFault(const char *scenario)
{
 allow_control_error=1U;
 if(!strcmp(scenario,"null_owner"))
 {
  unsigned before=ep0_ll_calls;
  assert(PcUsbControl_Dispatch(NULL)==USBD_FAIL);
  assert(ep0_ll_calls==before);return 1;
 }
 if(!strcmp(scenario,"foreign_owner"))
 {
  USBD_HandleTypeDef foreign=hUsbDeviceFS,original=foreign;
  unsigned before=ep0_ll_calls;
  assert(PcUsbControl_Dispatch(&foreign)==USBD_FAIL);
  assert(ep0_ll_calls==before && !memcmp(&foreign,&original,sizeof(foreign)));return 1;
 }
 if(!strcmp(scenario,"get_initial_failure"))
 {
  fail_ep0_tx_once=1U;
  assert(Request(0xA1U,CDC_GET_LINE_CODING,0U,7U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"set_initial_failure"))
 {
  fail_ep0_rx_once=1U;
  assert(Request(0x21U,CDC_SET_LINE_CODING,0U,7U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"status_tx_failure"))
 {
  fail_ep0_tx_once=1U;
  assert(Request(0x21U,CDC_SET_CONTROL_LINE_STATE,3U,0U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"status_rx_failure"))
 {
  assert(Request(0xA1U,CDC_GET_LINE_CODING,0U,7U)==USBD_OK);
  fail_ep0_rx_once=1U;
  assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,tx_ptr[0])==USBD_FAIL);
 }
 else if(!strcmp(scenario,"descriptor_continuation_failure"))
 {
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,0x0200U,255U)==USBD_OK);
  assert(tx_size[0]>64U);
  fail_ep0_tx_once=1U;
  assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,tx_ptr[0]+64U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"descriptor_initial_failure"))
 {
  fail_ep0_tx_once=1U;
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,0x0100U,18U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"descriptor_premature_rx_failure"))
 {
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,0x0200U,255U)==USBD_OK);
  assert(tx_size[0]>64U);
  fail_ep0_rx_once=1U;
  assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,tx_ptr[0]+64U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"receive_continuation_helper_failure"))
 {
  uint8_t data[7]={0};
  fail_ep0_rx_once=1U;
  assert(USBD_CtlContinueRx(&hUsbDeviceFS,data,sizeof(data))==USBD_FAIL);
  return 1; /* Direct helper contract; current seven-byte SET has no multi-packet OUT path. */
 }
 else {return 0;}
 FailureCheck();return 1;
}
'''


def _Replace_Once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


def test_exact_generated_control_faults(exact_control, tmp_path):
    normal.test_normal_stack_lifecycle_and_buffer_sessions(exact_control, tmp_path)
    baseline = json.loads((tmp_path / 'lifecycle-receipt.json').read_text(encoding='utf8'))
    source = (tmp_path / 'normal.c').read_text(encoding='utf8')
    source = '#include "pc_usb_control.h"\n#include "usbd_ioreq.h"\n' + source
    source = _Replace_Once(source, 'static unsigned fail_tx_once;',
        'static unsigned fail_tx_once;\nstatic unsigned fail_ep0_tx_once,fail_ep0_rx_once,ep0_ll_calls;')
    source = _Replace_Once(source, 'assert(d==&hUsbDeviceFS);tx_ptr',
        'assert(d==&hUsbDeviceFS);if((ep&0x7FU)==0U){ep0_ll_calls++;if(fail_ep0_tx_once){fail_ep0_tx_once=0U;return USBD_FAIL;}}tx_ptr')
    source = _Replace_Once(source, 'if(ep==0x01U && fail_prepare_once!=0U)',
        'if(ep==0U){ep0_ll_calls++;if(fail_ep0_rx_once){fail_ep0_rx_once=0U;return USBD_FAIL;}}\n if(ep==0x01U && fail_prepare_once!=0U)')
    source = _Replace_Once(source, 'int main(int argc,char **argv)', FAULTS + '\nint main(int argc,char **argv)')
    source = _Replace_Once(source, ' if(strcmp(argv[1],"control-boundaries")==0)',
        ' if(ControlFault(argv[1])){printf("PASS EP0 %s\\n",argv[1]);return 0;}\n if(strcmp(argv[1],"control-boundaries")==0)')
    (tmp_path / 'fault.c').write_text(source, encoding='utf8')
    command = [str(tmp_path / 'fault.c') if item.endswith('/normal.c') or item.endswith('\\normal.c') else
               str(tmp_path / 'fault.exe') if item.endswith('/normal.exe') or item.endswith('\\normal.exe') else item
               for item in baseline['command']]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (tmp_path / 'fault-compile.log').write_text(compiled.stdout + compiled.stderr, encoding='utf8')
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    runs = []
    for scenario in ('null_owner', 'foreign_owner', 'get_initial_failure', 'set_initial_failure',
                     'status_tx_failure', 'status_rx_failure', 'descriptor_continuation_failure',
                     'descriptor_initial_failure', 'descriptor_premature_rx_failure',
                     'receive_continuation_helper_failure'):
        invocation = [str(tmp_path / 'fault.exe'), scenario]
        result = subprocess.run(invocation, capture_output=True, text=True, timeout=20)
        runs.append({'command': invocation, 'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    receipt = {'part': exact_control[0], 'model_sha256': baseline['model_sha256'],
               'compiled_generated_sources_sha256': baseline['compiled_generated_sources_sha256'],
               'harness_sha256': hashlib.sha256(source.encode()).hexdigest(),
               'compile_command': command, 'compile_exit': compiled.returncode, 'runs': runs,
               'scope': 'Actual exact native core/class/EP0 policy and IO helpers; Host LL ports; no hardware or formal release claim'}
    (tmp_path / 'fault-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    assert all(row['exit'] == 0 for row in runs), runs
