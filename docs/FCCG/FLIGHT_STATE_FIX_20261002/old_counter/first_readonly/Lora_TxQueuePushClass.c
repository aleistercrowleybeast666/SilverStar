static uint8_t Lora_TxQueuePushClass(uint8_t instance, const uint8_t *data,
    uint8_t len, uint8_t control, uint32_t *transaction_id)
{
    uint32_t primask;
    uint32_t id = 0U;
    if ((data == NULL) || (len == 0U) || (len > LORA_MAX_PAYLOAD_LEN)) { return 0U; }
    primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance);
    uint8_t normal_capacity = (s_contexts[instance].schedule_role == LoraScheduleRole_Ground) ?
        LORA_TX_QUEUE_DEPTH : LORA_TX_NORMAL_QUEUE_DEPTH;
    if (s_contexts[instance].schedule_role == LoraScheduleRole_Ground) { control = 0U; }
    if (((control != 0U) && (s_tx_control_count >= LORA_TX_CONTROL_QUEUE_DEPTH)) ||
        ((control == 0U) && (((uint32_t)s_tx_count - (uint32_t)s_tx_control_count) >= normal_capacity)))
    { Lora_IrqUnlock(primask); return 0U; }
    if (transaction_id != NULL)
    {
        /* At most eight queued tokens plus one active token can collide. */
        for (uint8_t attempt = 0U; attempt < (LORA_TX_QUEUE_DEPTH + 2U); attempt++)
        {
            s_contexts[instance].next_tx_id = (s_contexts[instance].next_tx_id + 1U) & 0x00FFFFFFUL;
            if (s_contexts[instance].next_tx_id == 0U) { s_contexts[instance].next_tx_id = 1U; }
            id = ((uint32_t)instance << 24U) | s_contexts[instance].next_tx_id;
            if (Lora_TxIdPending(instance, id) == 0U) { break; }
        }
        SILVERSTAR_ASSERT(Lora_TxIdPending(instance, id) == 0U,
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
        if (id == s_contexts[instance].completed_tx_id) { s_contexts[instance].completed_tx_id = 0U; }
    }
    Lora_TxQueueInsert(instance, data, len, control, id);
    if (transaction_id != NULL) { *transaction_id = id; }
    Lora_IrqUnlock(primask);
    return 1U;
}
