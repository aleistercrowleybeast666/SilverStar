
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "usb_cdc_transport.h"
#include "silverstar_assert.h"
#define USBD_OK 0U
#define USBD_BUSY 1U
#define USBD_FAIL 2U
#define USBD_SPEED_FULL 1U
#define USBD_STATE_DEFAULT 1U
#define USBD_STATE_CONFIGURED 3U
#define USBD_STATE_SUSPENDED 4U
#define USBD_EP0_IDLE 0U
#define USBD_EP_TYPE_CTRL 0U
#define USBD_EP_TYPE_BULK 2U
#define USBD_EP_TYPE_INTR 3U
#define USB_MAX_EP0_SIZE 64U
#define CDC_IN_EP 0x81U
#define CDC_OUT_EP 1U
#define CDC_CMD_EP 0x82U
#define CDC_CMD_PACKET_SIZE 8U
#define CDC_DATA_FS_MAX_PACKET_SIZE 64U
#define CDC_DATA_FS_IN_PACKET_SIZE 64U
#define CDC_DATA_FS_OUT_PACKET_SIZE 64U
#define CDC_FS_BINTERVAL 16U
#define HAL_OK 0U
typedef uint8_t USBD_StatusTypeDef;
typedef struct USBD_Handle USBD_HandleTypeDef;
typedef struct { uint32_t total_length,maxpacket; uint8_t is_used,bInterval; } Endpoint;
typedef struct { uint8_t (*Init)(USBD_HandleTypeDef *,uint8_t); uint8_t (*DeInit)(USBD_HandleTypeDef *,uint8_t); } Class;
struct USBD_Handle {
 void *pData,*pClassData; void *pUserData;Class *pClass;
 uint8_t dev_state,dev_old_state,dev_speed,dev_config,dev_remote_wakeup,dev_test_mode,ep0_state,classId;
 Endpoint ep_in[16],ep_out[16];
};
typedef struct { uint32_t TxState,RxState,TxLength,RxLength; uint8_t *TxBuffer,*RxBuffer; uint8_t CmdOpCode,CmdLength; } USBD_CDC_HandleTypeDef;
typedef struct { int8_t (*Init)(void);int8_t (*DeInit)(void);int8_t (*Receive)(uint8_t *,uint32_t *);int8_t (*TransmitCplt)(uint8_t *,uint32_t *,uint8_t); } USBD_CDC_ItfTypeDef;
typedef struct { uint8_t *xfer_buff; uint32_t xfer_len,xfer_count,maxpacket; uint16_t pmaadress;uint8_t doublebuffer; } PCD_EPTypeDef;
typedef struct { uint32_t GINTSTS,GRXFSIZ,DIEPTXF0_HNPTXFSIZ,DIEPTXF[4],BTABLE; } GlobalRegs;
static GlobalRegs global_regs;
typedef struct { void *pData; GlobalRegs *Instance; struct { uint32_t dma_enable; } Init; PCD_EPTypeDef IN_ep[16],OUT_ep[16]; } PCD_HandleTypeDef;
#define USB (&global_regs)
#define USB_OTG_FS (&global_regs)
#define USB_OTG_FS_TOTAL_FIFO_SIZE 1280U
static USBD_HandleTypeDef hUsbDeviceFS;
static PCD_HandleTypeDef hpcd_USB_FS;
static USBD_CDC_HandleTypeDef storage;
static uint8_t UserRxBufferFS[64],UserTxBufferFS[256];
static unsigned prepared,transmitted,closed,aborted,cleared,mask;
static uint8_t fail_open,fail_prepare,fail_tx,fail_abort,fail_close,fail_flush,fail_readback;
static uint8_t stage_result;
static unsigned staged;
static uint32_t rx_length=64U;
static struct { uint32_t DIEPINT,DIEPCTL; } in_regs[16];
static struct { uint32_t DOEPINT,DOEPCTL; } out_regs[16];
static struct { uint32_t DIEPEMPMSK,DAINTMSK; } device_regs;
static uint16_t ep_regs[16];
#define USB_OTG_DIEPCTL_EPENA 1U
#define USB_OTG_DIEPCTL_USBAEP 2U
#define USB_OTG_DOEPCTL_EPENA 1U
#define USB_OTG_DOEPCTL_USBAEP 2U
#define USB_OTG_GINTSTS_RXFLVL 16U
#define USB_EPTX_STAT 0x30U
#define USB_EPRX_STAT 0x3000U
#define USB_EP_CTR_TX 0x80U
#define USB_EP_CTR_RX 0x8000U
#define PCD_GET_ENDPOINT(p,n) ((void)(p),ep_regs[n])
#define USBx_DEVICE ((void)USBx_BASE, &device_regs)
#define USBx_INEP(n) ((void)USBx_BASE, &in_regs[n])
#define USBx_OUTEP(n) ((void)USBx_BASE, &out_regs[n])
#define PCD_CLEAR_TX_EP_CTR(p,n) ((void)(p),(void)(n),cleared++)
#define PCD_CLEAR_RX_EP_CTR(p,n) ((void)(p),(void)(n),cleared++)
uint32_t UsbCdcPort_Lock(void) { unsigned old=mask;mask=1U;return old; }
void UsbCdcPort_Unlock(uint32_t old) { mask=old; }
void SilverStarAssert_Check(uint8_t ok,SilverStarAssertModuleId m,const char *f,uint32_t l,SilverStarAssertReasonId r)
{ (void)m;(void)f;(void)l;(void)r;assert(ok); }
static void *TestAlloc(size_t size) { assert(size==sizeof(storage));return &storage; }
static void TestFree(void *data) { assert(data==&storage); }
#define USBD_malloc TestAlloc
#define USBD_free TestFree
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *,uint8_t);
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *,uint8_t *,uint16_t);
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *,uint8_t *);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *);
uint8_t CDC_Transmit_FS(uint8_t *,uint16_t);
static uint8_t HAL_PCD_EP_Abort(PCD_HandleTypeDef *p,uint8_t address)
{ assert(p==&hpcd_USB_FS && mask==1U);(void)address;aborted++;return fail_abort; }
static uint8_t HAL_PCD_EP_Close(PCD_HandleTypeDef *p,uint8_t address)
{ assert(p==&hpcd_USB_FS && mask==1U);unsigned n=address&0x7FU;closed++;
  if(!fail_readback) { in_regs[n].DIEPCTL=0U;out_regs[n].DOEPCTL=0U;ep_regs[n]=0U; }
  return fail_close; }

static USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *p,uint8_t ep,uint8_t type,uint16_t size)
{ assert(p==&hUsbDeviceFS);(void)ep;(void)type;(void)size;return fail_open; }
static USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&hUsbDeviceFS && ep==1U && data==UserRxBufferFS && size==64U);prepared++;
  hpcd_USB_FS.OUT_ep[1].xfer_buff=data;hpcd_USB_FS.OUT_ep[1].xfer_len=size;hpcd_USB_FS.OUT_ep[1].xfer_count=0U;return fail_prepare; }
static USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&hUsbDeviceFS && (ep==1U || ep==0x81U) && size<=256U);hpcd_USB_FS.IN_ep[1].xfer_buff=data;transmitted++;return fail_tx; }
static uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *p,uint8_t ep)
{ assert(p==&hUsbDeviceFS && ep==1U);return rx_length; }

#include "usb_cdc_transport.h"
#include "usb_cdc_port.h"
#include "silverstar_assert.h"
#include <stddef.h>

static uint8_t s_rx[USB_CDC_RX_CAPACITY];
static uint8_t s_tx[USB_CDC_TX_CAPACITY];
static uint16_t s_head;
static uint16_t s_tail;
static uint16_t s_count;
static uint16_t s_tx_length;
static uint32_t s_session = 1U;
static uint8_t s_online;
static uint8_t s_exhausted;
static uint8_t s_submitted;
static uint8_t s_armed;
static uint8_t s_retired = 1U;

static void UsbCdc_Check(void)
{
    SILVERSTAR_ASSERT((s_head < USB_CDC_RX_CAPACITY) &&
        (s_tail < USB_CDC_RX_CAPACITY) && (s_count <= USB_CDC_RX_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT((s_tx_length <= USB_CDC_TX_CAPACITY) &&
        (s_submitted <= 1U) && ((s_submitted == 0U) || (s_tx_length != 0U)),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT(((s_head + USB_CDC_RX_CAPACITY - s_tail) %
        USB_CDC_RX_CAPACITY) == (s_count % USB_CDC_RX_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT((s_online <= 1U) && (s_armed <= 1U) &&
        (s_retired <= 1U) && (s_exhausted <= 1U) &&
        ((s_retired == 0U) || ((s_online == 0U) && (s_tx_length == 0U))),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

static void UsbCdc_Invalidate(void)
{
    s_online = 0U;
    s_armed = 0U;
    s_head = 0U;
    s_tail = 0U;
    s_count = 0U;
    if (s_session == UINT32_MAX) { s_exhausted = 1U; }
    else { s_session++; }
    /* Submitted bytes remain owned until explicit successful cancellation. */
}

void UsbCdc_LinkDown(void)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    UsbCdc_Invalidate();
    UsbCdcPort_Unlock(token);
}

UsbCdcResult UsbCdc_Quiesced(void)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if (s_online != 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    /* Caller has proved successful hardware retirement, not just timeout. */
    s_tx_length = 0U;
    s_submitted = 0U;
    s_retired = 1U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Configure(void)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if ((s_online != 0U) || (s_retired == 0U))
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    if (s_exhausted != 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    s_online = 1U;
    s_retired = 0U;
    /* The native class performs the first receive arm during Init. */
    s_armed = 1U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Receive(const uint8_t *data, uint16_t length)
{
    uint16_t index;
    uint32_t token;
    if ((data == NULL) || (length > USB_CDC_PACKET_SIZE))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if (s_online == 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    if ((s_armed == 0U) || (length > (USB_CDC_RX_CAPACITY - s_count)))
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    s_armed = 0U;
    for (index = 0U; index < USB_CDC_PACKET_SIZE; index++)
    {
        if (index >= length) { break; }
        s_rx[s_head] = data[index];
        s_head = (uint16_t)((s_head + 1U) % USB_CDC_RX_CAPACITY);
    }
    s_count = (uint16_t)(s_count + length);
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Read(uint8_t *data, uint16_t capacity,
    uint16_t *length, uint32_t *session)
{
    uint16_t count;
    uint32_t token;
    if ((data == NULL) || (length == NULL) || (session == NULL) ||
        (capacity == 0U)) { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    UsbCdc_Check();
    *length = 0U;
    *session = s_session;
    if (s_online == 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    for (count = 0U; count < USB_CDC_RX_CAPACITY; count++)
    {
        if ((count >= capacity) || (count >= s_count)) { break; }
        data[count] = s_rx[s_tail];
        s_tail = (uint16_t)((s_tail + 1U) % USB_CDC_RX_CAPACITY);
    }
    s_count = (uint16_t)(s_count - count);
    *length = count;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Write(const uint8_t *data, uint16_t length,
    uint32_t session)
{
    uint16_t index;
    uint32_t token;
    if ((data == NULL) || (length == 0U) || (length > USB_CDC_TX_CAPACITY))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if ((s_online == 0U) || (session != s_session))
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    if (s_tx_length != 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    for (index = 0U; index < USB_CDC_TX_CAPACITY; index++)
    {
        if (index >= length) { break; }
        s_tx[index] = data[index];
    }
    s_tx_length = length;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

static UsbCdcResult UsbCdc_TxService(void)
{
    UsbCdcResult result;
    if (s_tx_length == 0U) { return USB_CDC_OK; }
    result = UsbCdcPort_TxState();
    if (result != USB_CDC_OK) { return result; }
    if (s_submitted != 0U)
    {
        s_tx_length = 0U;
        s_submitted = 0U;
        return USB_CDC_OK;
    }
    result = UsbCdcPort_Submit(s_tx, s_tx_length);
    if (result == USB_CDC_OK) { s_submitted = 1U; }
    return result;
}

UsbCdcResult UsbCdc_Service(void)
{
    UsbCdcResult result;
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if (s_online == 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    result = UsbCdc_TxService();
    if ((result != USB_CDC_OK) && (result != USB_CDC_BUSY))
    {
        UsbCdc_Invalidate();
        UsbCdcPort_Unlock(token);
        return result;
    }
    if ((s_armed == 0U) &&
        ((USB_CDC_RX_CAPACITY - s_count) >= USB_CDC_PACKET_SIZE))
    {
        UsbCdcResult receive = UsbCdcPort_Rearm();
        if (receive == USB_CDC_OK) { s_armed = 1U; }
        else if (receive != USB_CDC_BUSY)
        { UsbCdc_Invalidate(); result = receive; }
        else { result = USB_CDC_BUSY; }
    }
    UsbCdcPort_Unlock(token);
    return result;
}

uint32_t UsbCdc_SessionGet(void)
{
    uint32_t token = UsbCdcPort_Lock();
    uint32_t session = s_session;
    UsbCdcPort_Unlock(token);
    return session;
}

static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[5] = {hpcd_USB_FS.OUT_ep[0].pmaadress, hpcd_USB_FS.IN_ep[0].pmaadress,
        hpcd_USB_FS.IN_ep[1].pmaadress, hpcd_USB_FS.OUT_ep[1].pmaadress, hpcd_USB_FS.IN_ep[2].pmaadress};
    const uint32_t size[5] = {64U, 64U, 64U, 64U, 8U};
    uint32_t i;
    uint32_t j;
    if ((hpcd_USB_FS.Instance->BTABLE != 0U) ||
        (hpcd_USB_FS.OUT_ep[0].doublebuffer != 0U) || (hpcd_USB_FS.IN_ep[0].doublebuffer != 0U) ||
        (hpcd_USB_FS.IN_ep[1].doublebuffer != 0U) || (hpcd_USB_FS.OUT_ep[1].doublebuffer != 0U) ||
        (hpcd_USB_FS.IN_ep[2].doublebuffer != 0U)) { return USB_CDC_FAULT; }
    /* Reviewed F1 single-buffer PMA: 512 bytes, three 8-byte table entries.
     * Offsets are read from CubeMX's effective configuration, not rewritten. */
    for (i = 0U; i < 5U; i++)
    {
        if ((start[i] < 24U) || ((start[i] % 2U) != 0U) || (start[i] > 512U) ||
            (size[i] > (512U - start[i]))) { return USB_CDC_FAULT; }
        for (j = 0U; j < 5U; j++)
        {
            if ((j < i) && (start[i] < (start[j] + size[j])) &&
                (start[j] < (start[i] + size[i]))) { return USB_CDC_FAULT; }
        }
    }
    return USB_CDC_OK;
}
UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdcResult result = USB_CDC_INVALID;
    if ((device == &hUsbDeviceFS) && (device->pData == &hpcd_USB_FS) &&
        (hpcd_USB_FS.Instance == USB))
    { result = UsbCdcRetire_MemoryCheck(); }
    if (result != USB_CDC_OK) { UsbCdc_LinkDown(); }
    UsbCdcPort_Unlock(token);
    return result;
}
static UsbCdcResult UsbCdcRetire_HardwareFinish(uint8_t address)
{
    uint8_t number = address & 0x7FU;
    if ((address & 0x80U) != 0U)
    {
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EPTX_STAT) != 0U)
        { return USB_CDC_FAULT; }
        PCD_CLEAR_TX_EP_CTR(hpcd_USB_FS.Instance, number);
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EP_CTR_TX) != 0U)
        { return USB_CDC_FAULT; }
    }
    else
    {
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EPRX_STAT) != 0U)
        { return USB_CDC_FAULT; }
        PCD_CLEAR_RX_EP_CTR(hpcd_USB_FS.Instance, number);
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EP_CTR_RX) != 0U)
        { return USB_CDC_FAULT; }
    }
    return USB_CDC_OK;
}
UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device, uint8_t address)
{
    PCD_EPTypeDef *ep;
    uint32_t token;
    uint8_t number = address & 0x7FU;
    if ((device != &hUsbDeviceFS) || (device->pData != &hpcd_USB_FS) ||
        ((address != 0x81U) && (address != 0x01U) && (address != 0x82U)))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    ep = ((address & 0x80U) != 0U) ? &hpcd_USB_FS.IN_ep[number] : &hpcd_USB_FS.OUT_ep[number];
    if ((HAL_PCD_EP_Abort(&hpcd_USB_FS, address) != HAL_OK) ||
        (HAL_PCD_EP_Close(&hpcd_USB_FS, address) != HAL_OK))
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    if (UsbCdcRetire_HardwareFinish(address) != USB_CDC_OK)
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    /* No DMA in these exact profiles. Disabled endpoints cannot consume more
     * CPU source bytes; clear pending completion and stale software pointers. */
    ep->xfer_buff = NULL;
    ep->xfer_len = 0U;
    ep->xfer_count = 0U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *pdev, uint8_t ep_addr)
{
  return (UsbCdcRetire_Endpoint(pdev, ep_addr) == USB_CDC_OK) ? USBD_OK : USBD_FAIL;
}
static uint8_t NativeCdc_Fault(USBD_HandleTypeDef *pdev)
{
  pdev->dev_state = USBD_STATE_DEFAULT;
  UsbCdc_LinkDown();
  return USBD_FAIL;
}
static uint8_t NativeCdc_InitAbort(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  uint8_t cleanup = USBD_CDC_DeInit(pdev, cfgidx);
  uint8_t failure = NativeCdc_Fault(pdev);
  /* Never turn successful cleanup into successful initialization. */
  return (cleanup == USBD_BUSY) ? USBD_BUSY : failure;
}
static uint8_t NativeCdc_Open(USBD_HandleTypeDef *pdev, uint8_t ep,
                            uint8_t type, uint16_t size)
{
  USBD_StatusTypeDef result = USBD_LL_OpenEP(pdev, ep, type, size);
  if (result != USBD_OK) { return (result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL; }
  if ((ep & 0x80U) != 0U) { pdev->ep_in[ep & 0x0FU].is_used = 1U; }
  else { pdev->ep_out[ep & 0x0FU].is_used = 1U; }
  return USBD_OK;
}
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_CDC_ItfTypeDef *itf;
  if ((pdev == NULL) || (pdev->dev_speed != USBD_SPEED_FULL) ||
      (pdev->pUserData == NULL) || (pdev->pClassData != NULL)) { return USBD_FAIL; }
  itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData;
  if ((itf->Init == NULL) || (itf->DeInit == NULL) || (itf->Receive == NULL) ||
      (pdev->ep_in[CDC_IN_EP & 0x0FU].is_used != 0U) ||
      (pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used != 0U) ||
      (pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used != 0U)) { return USBD_FAIL; }
  /* The recognized native configuration maps this to one static class block. */
  pdev->pClassData = USBD_malloc(sizeof(USBD_CDC_HandleTypeDef));
  if (pdev->pClassData == NULL) { return NativeCdc_Fault(pdev); }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  memset(hcdc, 0, sizeof(*hcdc));
  hcdc->CmdOpCode = 0xFFU;
  if ((NativeCdc_Open(pdev, CDC_IN_EP, USBD_EP_TYPE_BULK, CDC_DATA_FS_IN_PACKET_SIZE) != USBD_OK) ||
      (NativeCdc_Open(pdev, CDC_OUT_EP, USBD_EP_TYPE_BULK, CDC_DATA_FS_OUT_PACKET_SIZE) != USBD_OK) ||
      (NativeCdc_Open(pdev, CDC_CMD_EP, USBD_EP_TYPE_INTR, CDC_CMD_PACKET_SIZE) != USBD_OK))
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  if ((itf->Init() != (int8_t)USBD_OK) || (hcdc->RxBuffer == NULL) || (hcdc->TxBuffer == NULL))
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  if (USBD_LL_PrepareReceive(pdev, CDC_OUT_EP, hcdc->RxBuffer, CDC_DATA_FS_OUT_PACKET_SIZE) != USBD_OK)
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  return USBD_OK;
}
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  UsbCdc_LinkDown();

  uint8_t result = USBD_OK;
  USBD_CDC_ItfTypeDef *itf;
  /* There is one FS configuration; cleanup does not depend on its old index. */
  (void)cfgidx;
  if (pdev == NULL) { return USBD_FAIL; }
  if (pdev->ep_in[CDC_IN_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_IN_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_in[CDC_IN_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_OUT_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_CMD_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->pClassData != NULL)
  {
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
    hcdc->TxState = 1U; /* Retain buffer ownership until closure is confirmed. */
    itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData;
    if ((itf == NULL) || (itf->DeInit == NULL) || (itf->DeInit() != (int8_t)USBD_OK))
    { result = USBD_FAIL; }
    if (result == USBD_OK) { USBD_free(pdev->pClassData); pdev->pClassData = NULL; }
  }
  if (result != USBD_OK) { return NativeCdc_Fault(pdev); }
  if (UsbCdc_Quiesced() != USB_CDC_OK) { return USBD_FAIL; }
  return result;
}
static uint8_t USBD_CDC_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  USBD_CDC_HandleTypeDef *hcdc;
  PCD_HandleTypeDef *hpcd;
  if ((pdev == NULL) || (epnum != (CDC_IN_EP & 0x7FU)) || (pdev->pClassData == NULL) ||
      (pdev->pData == NULL) || (pdev->dev_state != USBD_STATE_CONFIGURED)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  hpcd = (PCD_HandleTypeDef *)pdev->pData;
  if (hpcd->IN_ep[epnum].maxpacket != CDC_DATA_FS_IN_PACKET_SIZE)
  { return NativeCdc_Fault(pdev); }
  if ((pdev->ep_in[epnum].total_length > 0U) &&
      ((pdev->ep_in[epnum].total_length % CDC_DATA_FS_IN_PACKET_SIZE) == 0U))
  {
    USBD_StatusTypeDef result;
    pdev->ep_in[epnum].total_length = 0U;
    result = USBD_LL_Transmit(pdev, epnum, NULL, 0U);
    if (result != USBD_OK)
    {
      uint8_t failure = NativeCdc_Fault(pdev);
      return (result == USBD_BUSY) ? USBD_BUSY : failure;
    }
  }
  else { hcdc->TxState = 0U; }
  return USBD_OK;
}
static uint8_t USBD_CDC_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_CDC_ItfTypeDef *itf;
  int8_t result;
  if ((pdev == NULL) || (epnum != (CDC_OUT_EP & 0x7FU)) || (pdev->pClassData == NULL) ||
      (pdev->pUserData == NULL) || (pdev->dev_state != USBD_STATE_CONFIGURED)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData;
  if ((hcdc->RxBuffer == NULL) || (itf->Receive == NULL)) { return NativeCdc_Fault(pdev); }
  hcdc->RxLength = USBD_LL_GetRxDataSize(pdev, epnum);
  if (hcdc->RxLength > CDC_DATA_FS_OUT_PACKET_SIZE) { return NativeCdc_Fault(pdev); }
  result = itf->Receive(hcdc->RxBuffer, &hcdc->RxLength);
  if (result != (int8_t)USBD_OK)
  {
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == (int8_t)USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *pdev)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->pClassData == NULL) ||
      (pdev->dev_state != USBD_STATE_CONFIGURED) || (pdev->dev_speed != USBD_SPEED_FULL))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  if (hcdc->TxState != 0U) { return USBD_BUSY; }
  if ((hcdc->TxBuffer == NULL) || (hcdc->TxLength == 0U) || (hcdc->TxLength > USB_CDC_TX_CAPACITY))
  { return USBD_FAIL; }
  hcdc->TxState = 1U;
  pdev->ep_in[CDC_IN_EP & 0x0FU].total_length = hcdc->TxLength;
  result = USBD_LL_Transmit(pdev, CDC_IN_EP, hcdc->TxBuffer, (uint16_t)hcdc->TxLength);
  if (result != USBD_OK)
  {
    /* A failed LL call cannot prove absence of partial DMA ownership. Keep
     * TxState and bytes owned until successful endpoint closure or reset. */
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *pdev)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->pClassData == NULL) || (pdev->dev_speed != USBD_SPEED_FULL))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  if (hcdc->RxBuffer == NULL) { return USBD_FAIL; }
  result = USBD_LL_PrepareReceive(pdev, CDC_OUT_EP, hcdc->RxBuffer, CDC_DATA_FS_OUT_PACKET_SIZE);
  if (result != USBD_OK)
  {
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *pdev, uint8_t *pbuff, uint16_t length)
{
  USBD_CDC_HandleTypeDef *hcdc;
  /* This private owner accepts the SCG-owned bounded transport chunk. */
  if ((pdev == NULL) || (pdev->pClassData == NULL) || (pbuff == NULL) || (length > USB_CDC_TX_CAPACITY))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  if (hcdc->TxState != 0U) { return USBD_BUSY; }
  hcdc->TxBuffer = pbuff; hcdc->TxLength = length;
  return USBD_OK;
}
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *pdev, uint8_t *pbuff)
{
  USBD_CDC_HandleTypeDef *hcdc;
  if ((pdev == NULL) || (pdev->pClassData == NULL) || (pbuff == NULL)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  hcdc->RxBuffer = pbuff;
  return USBD_OK;
}
USBD_StatusTypeDef USBD_SetClassConfig(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  if ((pdev != &hUsbDeviceFS) || (pdev->pClass == NULL) ||
      (pdev->pClass->Init == NULL))
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return USBD_FAIL; }
  if (UsbCdcRetire_ConfigurationCheck(pdev) != USB_CDC_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; return USBD_FAIL; }
  if (pdev->pClass->Init(pdev, cfgidx) != USBD_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return USBD_FAIL; }
  /* Init has opened the endpoints and checked the initial receive arm. */
  if (UsbCdc_Configure() != USB_CDC_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return USBD_FAIL; }
  return USBD_OK;
}
USBD_StatusTypeDef USBD_ClrClassConfig(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  UsbCdc_LinkDown();
  if ((pdev != &hUsbDeviceFS) || (pdev->pClass == NULL) ||
      (pdev->pClass->DeInit == NULL)) { return USBD_FAIL; }
  return (pdev->pClass->DeInit(pdev, cfgidx) == USBD_OK) ? USBD_OK : USBD_FAIL;
}
USBD_StatusTypeDef USBD_LL_Reset(USBD_HandleTypeDef *pdev)
{
  if ((pdev != &hUsbDeviceFS) || (pdev->pClass == NULL) ||
      (pdev->pClass->DeInit == NULL))
  { UsbCdc_LinkDown(); return USBD_FAIL; }

  if (pdev != &hUsbDeviceFS) { return USBD_FAIL; }
  UsbCdc_LinkDown();

  /* Open EP0 OUT */
  USBD_LL_OpenEP(pdev, 0x00U, USBD_EP_TYPE_CTRL, USB_MAX_EP0_SIZE);
  pdev->ep_out[0x00U & 0xFU].is_used = 1U;

  pdev->ep_out[0].maxpacket = USB_MAX_EP0_SIZE;

  /* Open EP0 IN */
  USBD_LL_OpenEP(pdev, 0x80U, USBD_EP_TYPE_CTRL, USB_MAX_EP0_SIZE);
  pdev->ep_in[0x80U & 0xFU].is_used = 1U;

  pdev->ep_in[0].maxpacket = USB_MAX_EP0_SIZE;

  /* Upon Reset call user call back */
  pdev->dev_state = USBD_STATE_DEFAULT;
  pdev->ep0_state = USBD_EP0_IDLE;
  pdev->dev_config = 0U;
  pdev->dev_remote_wakeup = 0U;

  if (pdev->pClassData)
  {
    if (pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config) != USBD_OK)
    { return USBD_FAIL; }
  }

  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_DevDisconnected(USBD_HandleTypeDef *pdev)
{
  if ((pdev != &hUsbDeviceFS) || (pdev->pClass == NULL) ||
      (pdev->pClass->DeInit == NULL))
  { UsbCdc_LinkDown(); return USBD_FAIL; }

  if (pdev != &hUsbDeviceFS) { return USBD_FAIL; }
  UsbCdc_LinkDown();

  /* Free Class Resources */
  pdev->dev_state = USBD_STATE_DEFAULT;
  if (pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config) != USBD_OK)
    { return USBD_FAIL; }

  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_Suspend(USBD_HandleTypeDef *pdev)
{
  if (pdev != &hUsbDeviceFS) { return USBD_FAIL; }
  UsbCdc_LinkDown();

  pdev->dev_old_state =  pdev->dev_state;
  pdev->dev_state  = USBD_STATE_SUSPENDED;

  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_Resume(USBD_HandleTypeDef *pdev)
{
  if (pdev->dev_state == USBD_STATE_SUSPENDED)
  {
    pdev->dev_state = pdev->dev_old_state;
  }

  return USBD_OK;
}
static int8_t CDC_Init_FS(void)
{
  _Static_assert(sizeof(UserRxBufferFS) >= USB_CDC_PACKET_SIZE,
      "native CDC RX buffer must fit the armed packet");
  if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0U) != USBD_OK)
  { return (int8_t)USBD_FAIL; }
  if (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS) != USBD_OK)
  { return (int8_t)USBD_FAIL; }
  return (int8_t)USBD_OK;
}
static int8_t CDC_DeInit_FS(void)
{
  UsbCdc_LinkDown();
  /* Class DeInit owns checked endpoint closure and transport retirement. */
  return (int8_t)USBD_OK;
}
static int8_t CDC_Receive_FS(uint8_t *data, uint32_t *length)
{
  if ((length == NULL) || (*length > USB_CDC_PACKET_SIZE) ||
      (UsbCdc_Receive(data, (uint16_t)*length) != USB_CDC_OK))
  { UsbCdc_LinkDown(); return (int8_t)USBD_FAIL; }
  /* Service alone rearms when a whole packet fits. */
  return (int8_t)USBD_OK;
}
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{
  uint8_t result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, data, length);
  if (result != USBD_OK) { return result; }
  return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}
UsbCdcResult UsbCdcPort_TxState(void)
{
    USBD_CDC_HandleTypeDef *cdc;

    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (hUsbDeviceFS.pClassData == NULL)) { return USB_CDC_OFFLINE; }
    cdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
    return (cdc->TxState == 0U) ? USB_CDC_OK : USB_CDC_BUSY;
}
UsbCdcResult UsbCdcPort_Submit(uint8_t *data, uint16_t length)
{
    uint8_t result;
    UsbCdcResult state = UsbCdcPort_TxState();
    if (state != USB_CDC_OK) { return state; }
    if ((data == NULL) || (length == 0U) || (length > USB_CDC_TX_CAPACITY))
    { return USB_CDC_INVALID; }
    result = CDC_Transmit_FS(data, length);
    /* Once called, even BUSY may hide a partial LL start. Require retirement. */
    return (result == USBD_OK) ? USB_CDC_OK : USB_CDC_FAULT;
}
UsbCdcResult UsbCdcPort_Rearm(void)
{
    uint8_t result;

    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (hUsbDeviceFS.pClassData == NULL)) { return USB_CDC_OFFLINE; }
    result = USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    /* Native rearm failure cannot prove absence of endpoint ownership. */
    return (result == USBD_OK) ? USB_CDC_OK : USB_CDC_FAULT;
}

USBD_StatusTypeDef USBD_LL_DataInStage(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data)
{ assert(p==&hUsbDeviceFS);(void)ep;(void)data;staged++;return stage_result; }
USBD_StatusTypeDef USBD_LL_DataOutStage(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data)
{ assert(p==&hUsbDeviceFS);(void)ep;(void)data;staged++;return stage_result; }
void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef *hpcd, uint8_t epnum)

{
  if ((hpcd != &hpcd_USB_FS) || (hpcd->pData != &hUsbDeviceFS) || (epnum > 2U))
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return; }
  if (hUsbDeviceFS.pClass == NULL)
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return; }
  if (USBD_LL_DataInStage(&hUsbDeviceFS, epnum, hpcd->IN_ep[epnum].xfer_buff) != USBD_OK)
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); }
}
void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef *hpcd, uint8_t epnum)

{
  if ((hpcd != &hpcd_USB_FS) || (hpcd->pData != &hUsbDeviceFS) || (epnum > 1U))
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return; }
  if (hUsbDeviceFS.pClass == NULL)
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return; }
  if (USBD_LL_DataOutStage(&hUsbDeviceFS, epnum, hpcd->OUT_ep[epnum].xfer_buff) != USBD_OK)
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); }
}

int main(int argc,char **argv)
{
 assert(argc==2);const char *scenario=argv[1];
 Class cls={USBD_CDC_Init,USBD_CDC_DeInit};
 USBD_CDC_ItfTypeDef itf={CDC_Init_FS,CDC_DeInit_FS,CDC_Receive_FS,NULL};
 hUsbDeviceFS.pClass=&cls;hUsbDeviceFS.pUserData=&itf;
 hUsbDeviceFS.pData=&hpcd_USB_FS;hUsbDeviceFS.dev_speed=USBD_SPEED_FULL;hpcd_USB_FS.IN_ep[1].maxpacket=64U;
 hpcd_USB_FS.Instance=&global_regs;hpcd_USB_FS.pData=&hUsbDeviceFS;hpcd_USB_FS.OUT_ep[1].xfer_buff=UserRxBufferFS;
 device_regs.DIEPEMPMSK=2U;
 hpcd_USB_FS.OUT_ep[0].pmaadress=0x18U;hpcd_USB_FS.IN_ep[0].pmaadress=0x58U;
 hpcd_USB_FS.IN_ep[1].pmaadress=0xC0U;hpcd_USB_FS.OUT_ep[1].pmaadress=0x110U;hpcd_USB_FS.IN_ep[2].pmaadress=0x100U;
 global_regs.GRXFSIZ=128U;global_regs.DIEPTXF0_HNPTXFSIZ=(64U<<16)|128U;
 global_regs.DIEPTXF[0]=(64U<<16)|192U;global_regs.DIEPTXF[1]=(16U<<16)|256U;
 if(strcmp(scenario,"init-arm-fail")==0) { fail_prepare=1U; }
 if(strcmp(scenario,"init-open-fail")==0) { fail_open=1U; }
 if(strcmp(scenario,"config-geometry")==0) { global_regs.BTABLE=64U;global_regs.GRXFSIZ=0U; }
 if(strcmp(scenario,"config-class-contract")==0) { cls.Init=NULL; }
 /* The native EP0 SetConfig path marks CONFIGURED before calling the class. */
 hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
 uint8_t configured=USBD_SetClassConfig(&hUsbDeviceFS,1U);
 uint8_t out[512],data[256];memset(data,0x39,sizeof(data));memset(UserRxBufferFS,0x72,sizeof(UserRxBufferFS));
 uint32_t session;uint16_t length;
 if(strcmp(scenario,"config-geometry")==0 || strcmp(scenario,"config-class-contract")==0)
 { assert(configured!=USBD_OK && prepared==0U && hUsbDeviceFS.dev_state==USBD_STATE_DEFAULT);
   assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(fail_prepare || fail_open)
 { assert(configured!=USBD_OK && hUsbDeviceFS.dev_state==USBD_STATE_DEFAULT);
   assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 assert(configured==USBD_OK && prepared==1U);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
 session=UsbCdc_SessionGet();
 if(strcmp(scenario,"bad-class-contract")==0)
 { cls.DeInit=NULL;assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);
   assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(strncmp(scenario,"callback-",9)==0)
 { if(strcmp(scenario,"callback-index")==0) { HAL_PCD_DataOutStageCallback(&hpcd_USB_FS,255U);assert(staged==0U); }
   if(strcmp(scenario,"callback-owner")==0) { PCD_HandleTypeDef wrong={0};HAL_PCD_DataInStageCallback(&wrong,1U);assert(staged==0U); }
   if(strcmp(scenario,"callback-error")==0) { stage_result=USBD_FAIL;HAL_PCD_DataOutStageCallback(&hpcd_USB_FS,1U);assert(staged==1U); }
   if(strcmp(scenario,"callback-null-class")==0) { hUsbDeviceFS.pClass=NULL;HAL_PCD_DataOutStageCallback(&hpcd_USB_FS,0U);assert(staged==0U); }
   if(strcmp(scenario,"callback-class-index")==0) { hUsbDeviceFS.classId=1U;HAL_PCD_DataInStageCallback(&hpcd_USB_FS,0U);assert(staged==0U); }
   assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(strcmp(scenario,"rx-length")==0)
 { uint32_t huge=65536U;assert(CDC_Receive_FS(UserRxBufferFS,&huge)!=USBD_OK);assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(strcmp(scenario,"rearm-failure")==0)
 { assert(USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK);fail_prepare=USBD_FAIL;
   assert(UsbCdc_Service()==USB_CDC_FAULT);assert(UsbCdc_Configure()==USB_CDC_BUSY);return 0; }
 for(unsigned i=0U;i<8U;i++)
 { assert(USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK);assert(UsbCdc_Service()==USB_CDC_OK); }
 assert(prepared==8U);assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OK && length==512U);
 for(unsigned i=0U;i<512U;i++) { assert(out[i]==0x72U); }
 assert(UsbCdc_Service()==USB_CDC_OK && prepared==9U);
 assert(UsbCdc_Write(data,256U,session)==USB_CDC_OK);
 if(strcmp(scenario,"tx-fail")==0) { fail_tx=USBD_FAIL; }
 UsbCdcResult submitted=UsbCdc_Service();
 if(fail_tx)
 { assert(submitted==USB_CDC_FAULT);assert(UsbCdc_Configure()==USB_CDC_BUSY);assert(hpcd_USB_FS.IN_ep[1].xfer_buff[0]==0x39U);return 0; }
 assert(submitted==USB_CDC_OK && storage.TxState==1U);
 uint8_t *owned=hpcd_USB_FS.IN_ep[1].xfer_buff;data[0]=0x18U;assert(owned[0]==0x39U);
 if(strcmp(scenario,"zlp-failure")==0)
 { fail_tx=USBD_FAIL;assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)!=USBD_OK);
   assert(storage.TxState==1U && UsbCdc_Configure()==USB_CDC_BUSY && owned[0]==0x39U);return 0; }
 if(strcmp(scenario,"abort-fail")==0) { fail_abort=1U; }
 if(strcmp(scenario,"close-fail")==0) { fail_close=1U; }
 if(strcmp(scenario,"flush-fail")==0) { fail_flush=1U; }
 if(strcmp(scenario,"retire-in-active")==0)
 { fail_readback=1U;in_regs[1].DIEPCTL=USB_OTG_DIEPCTL_EPENA;ep_regs[1]=USB_EPTX_STAT; }
 if(strcmp(scenario,"retire-out-active")==0)
 { fail_readback=1U;out_regs[1].DOEPCTL=USB_OTG_DOEPCTL_EPENA;ep_regs[1]=USB_EPRX_STAT; }
 if(strncmp(scenario,"retire-out-pending",18)==0) { global_regs.GINTSTS=USB_OTG_GINTSTS_RXFLVL; }
 if(fail_abort || fail_close || fail_flush || fail_readback || global_regs.GINTSTS)
 { assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);assert(hUsbDeviceFS.pClassData==&storage);
   assert(UsbCdc_Configure()==USB_CDC_BUSY && owned[0]==0x39U);assert(USBD_SetClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);
   if(global_regs.GINTSTS) { assert(hpcd_USB_FS.OUT_ep[1].xfer_buff==UserRxBufferFS); }
   if(strcmp(scenario,"retire-out-pending-retry")==0)
   { global_regs.GINTSTS=0U;assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)==USBD_OK);
     assert(USBD_SetClassConfig(&hUsbDeviceFS,1U)==USBD_OK);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
     assert(UsbCdc_Write(data,1U,session)==USB_CDC_OFFLINE);
     assert(USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK); }
   return 0; }
 if(strcmp(scenario,"suspend")==0)
 { assert(USBD_LL_Suspend(&hUsbDeviceFS)==USBD_OK);assert(USBD_LL_Resume(&hUsbDeviceFS)==USBD_OK);
   assert(UsbCdc_Write(data,1U,session)==USB_CDC_OFFLINE); }
 else
 { assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)==USBD_OK && storage.TxState==1U);assert(UsbCdc_Service()==USB_CDC_BUSY);
   assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)==USBD_OK && storage.TxState==0U);assert(UsbCdc_Service()==USB_CDC_OK); }
 if(strcmp(scenario,"disconnect")==0) { assert(USBD_LL_DevDisconnected(&hUsbDeviceFS)==USBD_OK); }
 else { assert(USBD_LL_Reset(&hUsbDeviceFS)==USBD_OK); }
 assert(hUsbDeviceFS.pClassData==NULL && hpcd_USB_FS.IN_ep[1].xfer_buff==NULL && aborted==3U && closed==3U);
 assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)!=USBD_OK && USBD_CDC_DataOut(&hUsbDeviceFS,1U)!=USBD_OK);
 assert(USBD_SetClassConfig(&hUsbDeviceFS,1U)==USBD_OK);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
 assert(UsbCdc_Write(data,1U,session)==USB_CDC_OFFLINE);session=UsbCdc_SessionGet();
 assert(UsbCdc_Write(data,1U,session)==USB_CDC_OK);return 0;
}
