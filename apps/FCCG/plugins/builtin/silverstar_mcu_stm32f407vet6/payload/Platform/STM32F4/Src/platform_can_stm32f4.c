#include "platform_can.h"

#include <stddef.h>
#include <string.h>

#include "platform_stm32f4_resources.h"
#include "stm32f4xx_hal.h"

static PlatformCanDiagnostics s_diagnostics[PLATFORM_CAN_COUNT];

static CAN_HandleTypeDef *PlatformCan_HandleGet(PlatformCanId id)
{
    return (CAN_HandleTypeDef *)PlatformStm32f4Resource_CanHandleGet(id);
}

static PlatformResult PlatformCan_ResultMap(HAL_StatusTypeDef result)
{
    if (result == HAL_OK) { return PLATFORM_OK; }
    if (result == HAL_TIMEOUT) { return PLATFORM_TIMEOUT; }
    if (result == HAL_BUSY) { return PLATFORM_BUSY; }
    return PLATFORM_IO_ERROR;
}

static uint8_t PlatformCan_FrameValid(const PlatformCanFrame *frame)
{
    if ((frame == NULL) || (frame->length > PLATFORM_CAN_DATA_MAX_LENGTH))
    {
        return 0U;
    }
    if (frame->extended_id != 0U)
    {
        return (frame->identifier <= 0x1FFFFFFFUL) ? 1U : 0U;
    }
    return (frame->identifier <= 0x7FFU) ? 1U : 0U;
}

static void PlatformCan_BusOffRefresh(PlatformCanId id, uint32_t error)
{
    PlatformCanDiagnostics *diagnostics = &s_diagnostics[id];

    if ((error & HAL_CAN_ERROR_BOF) != 0U)
    {
        if (diagnostics->bus_off == 0U) { diagnostics->bus_off_count++; }
        diagnostics->bus_off = 1U;
    }
    else
    {
        diagnostics->bus_off = 0U;
    }
}

static void PlatformCan_ErrorRefresh(PlatformCanId id,
                                     CAN_HandleTypeDef *handle)
{
    uint32_t error = HAL_CAN_GetError(handle);

    s_diagnostics[id].driver_error = error;
    PlatformCan_BusOffRefresh(id, error);
    if ((error & HAL_CAN_ERROR_RX_FOV0) != 0U)
    {
        s_diagnostics[id].rx_overrun_count++;
    }
}

static void PlatformCan_HeaderPrepare(const PlatformCanFrame *frame,
                                      CAN_TxHeaderTypeDef *header)
{
    (void)memset(header, 0, sizeof(*header));
    header->IDE = (frame->extended_id != 0U) ? CAN_ID_EXT : CAN_ID_STD;
    header->RTR = CAN_RTR_DATA;
    header->DLC = frame->length;
    header->ExtId = frame->identifier;
    header->StdId = frame->identifier;
}

static PlatformResult PlatformCan_MailboxWait(
    CAN_HandleTypeDef *handle, uint32_t timeout_ms)
{
    uint32_t start_tick = HAL_GetTick();
    uint32_t polls;

    for (polls = 0U; polls <= timeout_ms; polls++)
    {
        if (HAL_CAN_GetTxMailboxesFreeLevel(handle) > 0U) { return PLATFORM_OK; }
        if ((HAL_GetTick() - start_tick) >= timeout_ms) { return PLATFORM_TIMEOUT; }
    }
    return PLATFORM_TIMEOUT;
}

static void PlatformCan_FrameLoad(const CAN_RxHeaderTypeDef *header,
                                  PlatformCanFrame *frame)
{
    frame->extended_id = (header->IDE == CAN_ID_EXT) ? 1U : 0U;
    frame->identifier = (frame->extended_id != 0U) ?
        header->ExtId : header->StdId;
    frame->length = (header->DLC <= PLATFORM_CAN_DATA_MAX_LENGTH) ?
        (uint8_t)header->DLC : PLATFORM_CAN_DATA_MAX_LENGTH;
}

static PlatformResult PlatformCan_MessageSend(
    PlatformCanId id, CAN_HandleTypeDef *handle,
    const PlatformCanFrame *frame, CAN_TxHeaderTypeDef *header)
{
    uint32_t mailbox = 0U;
    HAL_StatusTypeDef result = HAL_CAN_AddTxMessage(
        handle, header, (uint8_t *)(uintptr_t)frame->data, &mailbox);

    PlatformCan_ErrorRefresh(id, handle);
    if (result == HAL_OK) { s_diagnostics[id].tx_count++; }
    return PlatformCan_ResultMap(result);
}

static PlatformResult PlatformCan_MessageReceive(
    PlatformCanId id, CAN_HandleTypeDef *handle, PlatformCanFrame *frame)
{
    CAN_RxHeaderTypeDef header;
    HAL_StatusTypeDef result;

    (void)memset(&header, 0, sizeof(header));
    (void)memset(frame, 0, sizeof(*frame));
    result = HAL_CAN_GetRxMessage(handle, CAN_RX_FIFO0, &header, frame->data);
    PlatformCan_ErrorRefresh(id, handle);
    if (result != HAL_OK) { return PlatformCan_ResultMap(result); }
    PlatformCan_FrameLoad(&header, frame);
    s_diagnostics[id].rx_count++;
    return PLATFORM_OK;
}

PlatformResult PlatformCan_Start(PlatformCanId id)
{
    CAN_HandleTypeDef *handle = PlatformCan_HandleGet(id);
    HAL_StatusTypeDef result;

    if (handle == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    result = HAL_CAN_Start(handle);
    PlatformCan_ErrorRefresh(id, handle);
    if (result == HAL_OK) { s_diagnostics[id].started = 1U; }
    return PlatformCan_ResultMap(result);
}

PlatformResult PlatformCan_Stop(PlatformCanId id)
{
    CAN_HandleTypeDef *handle = PlatformCan_HandleGet(id);
    HAL_StatusTypeDef result;

    if (handle == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    result = HAL_CAN_Stop(handle);
    PlatformCan_ErrorRefresh(id, handle);
    if (result == HAL_OK) { s_diagnostics[id].started = 0U; }
    return PlatformCan_ResultMap(result);
}

PlatformResult PlatformCan_Send(PlatformCanId id,
                                const PlatformCanFrame *frame,
                                uint32_t timeout_ms)
{
    CAN_HandleTypeDef *handle = PlatformCan_HandleGet(id);
    CAN_TxHeaderTypeDef header;
    PlatformResult wait_result;

    if ((handle == NULL) || (PlatformCan_FrameValid(frame) == 0U) ||
        (timeout_ms == 0U) ||
        (timeout_ms > PLATFORM_CAN_SEND_TIMEOUT_MAX_MS))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    PlatformCan_HeaderPrepare(frame, &header);
    wait_result = PlatformCan_MailboxWait(handle, timeout_ms);
    if (wait_result != PLATFORM_OK) { return wait_result; }
    return PlatformCan_MessageSend(id, handle, frame, &header);
}

PlatformResult PlatformCan_ReceivePoll(PlatformCanId id,
                                       PlatformCanFrame *frame)
{
    CAN_HandleTypeDef *handle = PlatformCan_HandleGet(id);

    if ((handle == NULL) || (frame == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    if (HAL_CAN_GetRxFifoFillLevel(handle, CAN_RX_FIFO0) == 0U)
    {
        PlatformCan_ErrorRefresh(id, handle);
        return PLATFORM_NOT_READY;
    }
    return PlatformCan_MessageReceive(id, handle, frame);
}

PlatformResult PlatformCan_DiagnosticsGet(
    PlatformCanId id,
    PlatformCanDiagnostics *diagnostics)
{
    CAN_HandleTypeDef *handle = PlatformCan_HandleGet(id);

    if ((handle == NULL) || (diagnostics == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    PlatformCan_ErrorRefresh(id, handle);
    *diagnostics = s_diagnostics[id];
    return PLATFORM_OK;
}
