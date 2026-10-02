static SystemDeviceResult Sx1281Transport_Send(uint8_t instance, const uint8_t *data,
                                                uint16_t length)
{
    (void)instance;
    LoraTxEnqueueResult result;

    if ((data == NULL) || (length == 0U) ||
        (length > LORA_MAX_PAYLOAD_LEN) || (length > UINT8_MAX))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    result = Lora_TxEnqueue(instance, data, (uint8_t)length);
    if (result == LORA_TX_ENQUEUE_OK) { return SYSTEM_DEVICE_OK; }
    if (result == LORA_TX_ENQUEUE_QUEUE_FULL) { return SYSTEM_DEVICE_NOT_READY; }
    if (result == LORA_TX_ENQUEUE_NOT_INIT) { return SYSTEM_DEVICE_OFFLINE; }
    return SYSTEM_DEVICE_INVALID_ARGUMENT;
}
