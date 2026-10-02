from pathlib import Path
import sys,subprocess
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002')
source=repo/'apps/FCCG/plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Src/jy901b_device.c'
text=source.read_text(encoding='utf8')
start=text.index('static uint8_t IMU_ParseReadResponseByte(')
end=text.index('Jy901bRegisterReadStartResult IMU_RegisterReadAsyncStart(',start)
text=text[:start]+'''static uint8_t IMU_ParseReadResponseByte(uint8_t byte, uint8_t *frame, uint8_t *idx)
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

''' +text[end:]
start=text.index('Jy901bRegisterReadPollResult IMU_RegisterReadAsyncPoll(')
end=text.index('Jy901bRegisterWriteStartResult IMU_RegisterWriteAsyncStart(',start)
text=text[:start]+'''static Jy901bRegisterReadPollResult IMU_RegisterReadDrain(
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

''' + text[end:]
source.write_text(text,encoding='utf8',newline='\n')
review=repo/'.work/imu_repair_review'
if review.exists():raise FileExistsError(review)
review.mkdir(parents=True)
git=['git','-c','safe.directory='+str(repo).replace('\\','/'),'-C',str(repo)]
diff=subprocess.run(git+['diff','--',str(source.relative_to(repo)).replace('\\','/')],check=True,capture_output=True).stdout
(review/'minimal_production.diff').write_bytes(diff)
original=subprocess.run(git+['show','492f30880e9936a7b72091b14354a21b32af33c4:'+str(source.relative_to(repo)).replace('\\','/')],check=True,capture_output=True).stdout
(review/'original_jy901b_device.c.txt').write_bytes(original)
(review/'patched_jy901b_device.c.txt').write_bytes(source.read_bytes())
print(str(review),flush=True)
