### IMU_ReadResponseChecksumValid

```c
static uint8_t IMU_ReadResponseChecksumValid(const uint8_t *frame)
{
    uint8_t sum = 0U;
    uint8_t i;

    if (frame == NULL) { return 0U; }
    for (i = 0U; i < (IMU_FRAME_LEN - 1U); i++)
    {
        sum = (uint8_t)(sum + frame[i]);
    }
    return (sum == frame[IMU_FRAME_LEN - 1U]) ? 1U : 0U;
}
```

### IMU_ParseReadResponseByte

```c
static uint8_t IMU_ParseReadResponseByte(uint8_t byte, uint8_t *frame, uint8_t *idx)
{
    uint8_t next;

    if ((frame == NULL) || (idx == NULL)) { return 0U; }
    SILVERSTAR_ASSERT(*idx < IMU_FRAME_LEN,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if ((*idx == 0U) && (byte != IMU_FRAME_HEADER)) { return 0U; }
    frame[*idx] = byte;
    (*idx)++;
    if (*idx < IMU_FRAME_LEN) { return 0U; }
    if (IMU_ReadResponseChecksumValid(frame) != 0U)
    {
        *idx = 0U;
        /* Consume a whole legal stream frame; never inspect its payload
         * for a register-response header. Both frame kinds share the CRC. */
        return (uint8_t)(frame[1] == IMU_REG_READ_RESPONSE);
    }
    /* A corrupt/truncated candidate may have swallowed the next header.
     * Retain its earliest bounded suffix, including an incomplete header. */
    *idx = 0U;
    for (next = 1U; next < IMU_FRAME_LEN; next++)
    {
        if (frame[next] == IMU_FRAME_HEADER)
        {
            *idx = (uint8_t)(IMU_FRAME_LEN - next);
            (void)memmove(frame, &frame[next], *idx);
            break;
        }
    }
    return 0U;
}
```

### IMU_RegisterReadDrain

```c
static Jy901bRegisterReadPollResult IMU_RegisterReadDrain(
    uint8_t instance, Jy901bContext *context, uint16_t *value)
{
    uint8_t buffer[IMU_TEMP_BUF_LEN];
    uint16_t remaining;
    uint16_t capacity;
    uint16_t read_length;
    uint16_t index;
    uint32_t chunk;

    if (PlatformUart_RxCountGet(Jy901bResource_UartGet(instance),
            &remaining) != PLATFORM_OK)
    { return Jy901bRegisterReadPollResult_IoError; }
    /* Snapshot the queue once: newly arriving data cannot extend this poll.
     * No byte timestamps exist; a poll after the deadline is conservative. */
    for (chunk = 0U; (chunk < IMU_MAX_READ_CHUNKS_PER_PROCESS) &&
            (remaining != 0U); chunk++)
    {
        if ((uint32_t)(PlatformTime_Ms() - context->register_read_started_ms) >
                IMU_CONFIG_READ_TIMEOUT_MS)
        { return Jy901bRegisterReadPollResult_Timeout; }
        capacity = (remaining < sizeof(buffer)) ? remaining : sizeof(buffer);
        if (PlatformUart_Read(Jy901bResource_UartGet(instance), buffer,
                capacity, &read_length) != PLATFORM_OK)
        { return Jy901bRegisterReadPollResult_IoError; }
        SILVERSTAR_ASSERT(read_length <= capacity,
            SILVERSTAR_ASSERT_MODULE_DEVICE,
            SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        if (read_length == 0U) { break; }
        remaining = (uint16_t)(remaining - read_length);
        for (index = 0U; index < read_length; index++)
        {
            if (IMU_ParseReadResponseByte(buffer[index],
                    context->register_read_frame,
                    &context->register_read_index) != 0U)
            {
                if ((uint32_t)(PlatformTime_Ms() -
                        context->register_read_started_ms) >
                        IMU_CONFIG_READ_TIMEOUT_MS)
                { return Jy901bRegisterReadPollResult_Timeout; }
                *value = (uint16_t)(((uint16_t)context->register_read_frame[3] << 8) |
                                    context->register_read_frame[2]);
                return Jy901bRegisterReadPollResult_Complete;
            }
        }
    }
    return Jy901bRegisterReadPollResult_Pending;
}
```

### IMU_RegisterReadAsyncPoll

```c
Jy901bRegisterReadPollResult IMU_RegisterReadAsyncPoll(
    uint8_t instance, uint16_t *value)
{
    Jy901bContext *context;
    Jy901bRegisterReadPollResult result;

    if ((instance >= PROJECT_JY901B_INSTANCE_COUNT) || (value == NULL))
    { return Jy901bRegisterReadPollResult_NotReady; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT(context->register_read_index < IMU_FRAME_LEN,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if (context->register_read_active == 0U)
    { return Jy901bRegisterReadPollResult_NotReady; }
    if ((uint32_t)(PlatformTime_Ms() - context->register_read_started_ms) >
            IMU_CONFIG_READ_TIMEOUT_MS)
    { result = Jy901bRegisterReadPollResult_Timeout; }
    else
    { result = IMU_RegisterReadDrain(instance, context, value); }
    if ((result == Jy901bRegisterReadPollResult_Pending) &&
        ((uint32_t)(PlatformTime_Ms() - context->register_read_started_ms) >=
         IMU_CONFIG_READ_TIMEOUT_MS))
    { result = Jy901bRegisterReadPollResult_Timeout; }
    if (result != Jy901bRegisterReadPollResult_Pending)
    { context->register_read_active = 0U; }
    return result;
}
```

### IMU_RegisterReadAsyncStart

```c
Jy901bRegisterReadStartResult IMU_RegisterReadAsyncStart(
    uint8_t instance, uint8_t reg)
{
    uint8_t cmd[IMU_CFG_FRAME_LEN] =
        {0xFFU, 0xAAU, IMU_REG_READADDR, reg, 0x00U};
    Jy901bContext *context;

    if (instance >= PROJECT_JY901B_INSTANCE_COUNT)
    { return Jy901bRegisterReadStartResult_InvalidArgument; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT_OBJECT(context, Jy901bContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->register_write_phase <= 2U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((context->register_read_active != 0U) ||
        (context->register_write_phase != 0U))
    { return Jy901bRegisterReadStartResult_Busy; }
    if (PlatformUart_RxFlush(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    { return Jy901bRegisterReadStartResult_IoError; }
    {
        PlatformResult send_result = PlatformUart_WriteFrameAsync(
            Jy901bResource_UartGet(instance), cmd, sizeof(cmd),
            PLATFORM_UART_TX_PRIORITY);
        if (send_result == PLATFORM_BUSY)
        { return Jy901bRegisterReadStartResult_Busy; }
        if (send_result != PLATFORM_OK)
        { return Jy901bRegisterReadStartResult_IoError; }
    }
    context->register_read_index = 0U;
    context->register_read_started_ms = PlatformTime_Ms();
    context->register_read_active = 1U;
    return Jy901bRegisterReadStartResult_Ok;
}
```

### IMU_ReadRegister

```c
static IMUState IMU_ReadRegister(uint8_t instance, uint8_t reg, uint16_t *value)
{
    uint8_t cmd[IMU_CFG_FRAME_LEN];
    uint8_t rxBuf[IMU_TEMP_BUF_LEN];
    uint8_t frame[IMU_FRAME_LEN];
    uint8_t idx = 0U;
    uint16_t readLen;
    uint16_t i;
    uint32_t startTick;
    uint32_t poll;

    if (value == NULL)
    {
        return IMU_NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    cmd[0] = 0xFFU;
    cmd[1] = 0xAAU;
    cmd[2] = IMU_REG_READADDR;
    cmd[3] = reg;
    cmd[4] = 0x00U;

    /*
     * The Platform UART backend owns the receive mechanism. Register reads
     * only consume its byte stream and never switch to a competing RX path.
     */
    (void)PlatformUart_RxFlush(Jy901bResource_UartGet(instance));

    if (PlatformUart_Write(Jy901bResource_UartGet(instance), cmd, sizeof(cmd),
                           IMU_CFG_TX_TIMEOUT_MS) != PLATFORM_OK)
    {
        PlatformTime_DelayMs(IMU_CONFIG_REG_GAP_MS);
        return IMU_UART_TX_ERROR;
    }

    startTick = PlatformTime_Ms();
    for (poll = 0U; poll < IMU_CONFIG_READ_MAX_POLLS; poll++)
    {
        if ((PlatformTime_Ms() - startTick) >= IMU_CONFIG_READ_TIMEOUT_MS)
        {
            break;
        }
        if (PlatformUart_Read(Jy901bResource_UartGet(instance), rxBuf, sizeof(rxBuf),
                              &readLen) != PLATFORM_OK)
        {
            return IMU_UART_RX_ERROR;
        }
        if (readLen == 0U)
        {
            PlatformTime_DelayMs(1U);
            continue;
        }

        for (i = 0U; (i < readLen) && (i < IMU_TEMP_BUF_LEN); i++)
        {
            if (IMU_ParseReadResponseByte(rxBuf[i], frame, &idx) != 0U)
            {
                *value = (uint16_t)(((uint16_t)frame[3] << 8) | frame[2]);
                PlatformTime_DelayMs(IMU_CONFIG_REG_GAP_MS);
                return IMU_OK;
            }
        }
    }

    PlatformTime_DelayMs(IMU_CONFIG_REG_GAP_MS);
    return IMU_RESP_TIMEOUT;
}
```

### IMU_Poll

```c
void IMU_Poll(uint8_t instance)
{
    uint8_t tempBuf[IMU_TEMP_BUF_LEN];
    PlatformUartDiagnostics port_diagnostics;
    uint16_t readLen;
    uint16_t i;
    uint32_t now;
    uint32_t chunk;

    SILVERSTAR_ASSERT_OBJECT(&s_imu, IMUData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((s_contexts[instance].register_read_active != 0U) ||
        (s_contexts[instance].register_write_phase != 0U))
    { return; }
    if (PlatformUart_DiagnosticsGet(Jy901bResource_UartGet(instance), &port_diagnostics) !=
        PLATFORM_OK)
    {
        return;
    }
    if (port_diagnostics.rx_discontinuity_count !=
        s_portDiscontinuitySequence)
    {
        IMU_ParserReset(instance);
        s_parserResyncCount++;
        s_portDiscontinuitySequence =
            port_diagnostics.rx_discontinuity_count;
    }

    readLen = 0U;
    for (chunk = 0U; chunk < IMU_MAX_READ_CHUNKS_PER_PROCESS; chunk++)
    {
        if (PlatformUart_Read(Jy901bResource_UartGet(instance), tempBuf, sizeof(tempBuf),
                              &readLen) != PLATFORM_OK)
        {
            return;
        }
        for (i = 0U; (i < readLen) && (i < IMU_TEMP_BUF_LEN); i++)
        {
            IMU_ParseByte(instance, tempBuf[i]);
        }
        if (readLen == 0U) { break; }
    }
    if ((chunk == IMU_MAX_READ_CHUNKS_PER_PROCESS) && (readLen != 0U))
    {
        s_processLimitCount++;
    }

    /* Decoding may publish a timestamp newer than the poll entry tick. */
    now = PlatformTime_Ms();
    if ((s_imu.ValidMask == 0U) ||
        ((now - s_imu.LastUpdateTickMs) > IMU_ONLINE_TIMEOUT_MS))
    {
        s_imu.Online = 0U;
    }
}
```
