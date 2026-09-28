#ifndef __SX1281_DEVICE_H
#define __SX1281_DEVICE_H

#include <stdint.h>
#include "sx1281_config.h"

typedef enum
{
    LORA_RADIO_STATE_NOT_INIT = 0U,
    LORA_RADIO_STATE_READY    = 1U,
    LORA_RADIO_STATE_RX       = 2U,
    LORA_RADIO_STATE_TX       = 3U,
    LORA_RADIO_STATE_BUSY     = 4U
} LoraRadioState;

typedef enum
{
    LORA_TX_ENQUEUE_OK = 0U,
    LORA_TX_ENQUEUE_NOT_INIT,
    LORA_TX_ENQUEUE_BAD_PARAM,
    LORA_TX_ENQUEUE_QUEUE_FULL
} LoraTxEnqueueResult;

typedef enum
{
    LORA_RX_DEQUEUE_OK = 0U,
    LORA_RX_DEQUEUE_EMPTY,
    LORA_RX_DEQUEUE_BAD_PARAM
} LoraRxDequeueResult;

typedef enum
{
    LORA_BUSY_IDLE = 0U,
    LORA_BUSY_ACTIVE = 1U
} LoraBusyState;

typedef enum
{
    LORA_DIAG_RESULT_OK = 0U,
    LORA_DIAG_RESULT_NOT_INIT,
    LORA_DIAG_RESULT_QUEUED,
    LORA_DIAG_RESULT_BUSY,
    LORA_DIAG_RESULT_TIMEOUT
} LoraDiagResult;

typedef enum
{
    LORA_CONTROL_IRQ_CLEAR = 0U,
    LORA_CONTROL_FORCE_RX_CONTINUOUS
} LoraControlOperation;

typedef enum
{
    LORA_CONTROL_SUBMIT_OK = 0U,
    LORA_CONTROL_SUBMIT_BUSY,
    LORA_CONTROL_SUBMIT_NOT_INIT,
    LORA_CONTROL_SUBMIT_BAD_PARAM
} LoraControlSubmitResult;

typedef enum
{
    LORA_CONTROL_GET_COMPLETE = 0U,
    LORA_CONTROL_GET_PENDING,
    LORA_CONTROL_GET_NOT_FOUND,
    LORA_CONTROL_GET_BAD_PARAM
} LoraControlGetResult;

typedef struct
{
    uint32_t transaction_id;
    LoraDiagResult result;
    uint16_t raw_irq_before;
} LoraControlResult;

typedef enum
{
    LORA_INIT_OK = 0U,
    LORA_INIT_PORT_ERROR,
    LORA_INIT_CHIP_NOT_FOUND
} LoraInitResult;

typedef enum
{
    LORA_CONFIG_OK = 0U,
    LORA_CONFIG_NOT_INIT,
    LORA_CONFIG_PORT_ERROR
} LoraConfigResult;

typedef struct
{
    uint16_t firmware_version;
    uint8_t status_value;
    uint8_t verified;
} LoraChipStatus;

typedef struct
{
    uint32_t tx_ok;
    uint32_t tx_dropped;
    uint32_t tx_timeout;
    uint32_t rx_ok;
    uint32_t rx_dropped;
    uint32_t rx_timeout;
    uint32_t rx_error;
    uint32_t rx_crc_error;
    uint8_t last_rx_len;
    int8_t last_rx_rssi;
    int8_t last_rx_snr;
    uint8_t last_rx_type;
    uint32_t rx_irq_count;
    uint32_t tx_irq_count;
    uint32_t rx_error_irq_count;
    uint32_t tx_timeout_irq_count;
    uint32_t rx_timeout_irq_count;
    LoraRadioState radio_state;
} LoraStats;

typedef struct
{
    uint8_t initialized;
    uint8_t busy_gpio;
    uint8_t dio1_gpio;
    uint8_t tx_queue_count;
    uint8_t rx_queue_count;
    LoraStats stats;
} LoraDebugSnapshot;

typedef struct
{
    uint16_t raw_irq;
    uint16_t last_raw_irq;
    uint16_t irq_mask;
    uint16_t dio1_mask;
    uint16_t dio2_mask;
    uint16_t dio3_mask;
    uint32_t setrx_count;
    uint32_t settx_count;
    uint32_t tx_start_count;
    uint32_t tx_done_count;
    uint32_t tx_timeout_count;
    uint32_t rx_start_count;
    uint32_t rx_done_count;
    uint32_t rx_crc_count;
    uint32_t rx_header_count;
    uint32_t rx_timeout_count;
    uint32_t rx_error_count;
    uint32_t last_setrx_ms;
    uint32_t last_settx_ms;
    uint32_t last_irq_ms;
    uint32_t last_rx_irq_ms;
    uint32_t last_tx_irq_ms;
    uint8_t has_last_irq;
    uint8_t has_last_rx_irq;
    uint8_t has_last_tx_irq;
    uint8_t packet_runtime;
    uint8_t rssi_inst_valid;
    int16_t rssi_inst;
} LoraDiagSnapshot;

LoraInitResult Lora_Init(uint8_t instance);
/* Bootstrap or Transport-owner context only. */
LoraConfigResult Lora_ApplyDefaultConfig(uint8_t instance);
void Lora_Process(uint8_t instance);
void Lora_StartRx(uint8_t instance);

LoraTxEnqueueResult Lora_TxEnqueue(uint8_t instance, const uint8_t *data, uint8_t len);
LoraTxEnqueueResult Lora_TxEnqueuePriority(uint8_t instance, const uint8_t *data, uint8_t len);
LoraRxDequeueResult Lora_RxDequeue(uint8_t instance, uint8_t *data, uint8_t *len, int8_t *rssi, int8_t *snr);

void Lora_GetStats(uint8_t instance, LoraStats *stats);
void Lora_GetDebugSnapshot(uint8_t instance, LoraDebugSnapshot *snapshot);
void Lora_GetDiagSnapshot(uint8_t instance, LoraDiagSnapshot *snapshot);
LoraDiagResult Lora_IrqClear(uint8_t instance, uint16_t *raw_before);
LoraDiagResult Lora_ForceRxContinuous(uint8_t instance);
LoraControlSubmitResult Lora_ControlSubmit(uint8_t instance, LoraControlOperation operation,
                                           uint32_t timeout_ms,
                                           uint32_t *transaction_id);
LoraControlGetResult Lora_ControlResultGet(uint8_t instance, uint32_t transaction_id,
                                           LoraControlResult *result);
void Lora_ClearStats(uint8_t instance);
LoraBusyState Lora_IsBusy(uint8_t instance);
LoraDiagResult Lora_ChipStatusGet(uint8_t instance, LoraChipStatus *status);

#endif /* __SX1281_DEVICE_H */
