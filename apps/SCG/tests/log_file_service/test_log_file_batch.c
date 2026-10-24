/* Synthetic backend; real service and adapter. No target/TF operation. */
#define main LegacyFixture_Main
#include "test_log_file_service.c"
#undef main

static char s_token[32];
static uint8_t s_frame[SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE];
static uint16_t s_length;

static void Metadata(uint32_t size)
{
    unsigned int id;
    s_pattern_enabled = 1U; s_pattern_size = size;
    id = Submit("LOGFILE META 1"); Finish(id);
    assert(strstr(s_reply, "token="));
    assert(sscanf(strstr(s_reply, "token="), "token=%31s", s_token) == 1);
}

static unsigned int Batch(uint32_t offset)
{
    char line[160];
    assert(snprintf(line, sizeof(line), "LOGFILE BATCH 1 %s %lu 1122334455667788 %lu",
        s_token, (unsigned long)offset, (unsigned long)(offset / 512U)) > 0);
    return Submit(line);
}

static void Get(void)
{
    uint32_t before = s_io_count;
    assert(SystemLogFile_BatchResponseGet(s_frame, sizeof(s_frame), &s_length) == SystemLogFileResult_Ok);
    assert(s_io_count == before && s_length <= sizeof(s_frame) && s_length != 0U);
}

static void Emit(void)
{
    assert(s_frame[0] == 0U && s_frame[s_length - 1U] == 0U);
    printf("FRAME_HEX ");
    for (uint16_t i = 0U; i < s_length; i++) { printf("%02X", s_frame[i]); }
    puts("");
    SystemLogFile_BatchResponseSent(1U);
}

static void Cancel(void)
{
    Execute("LOGFILE CANCEL");
    assert(strstr(s_reply, "cleanup_complete=0"));
    SystemLogFile_Process(1U);
    assert(s_live_handles == 0U);
}

static void Boundary(uint32_t size)
{
    uint32_t offset = 0U;
    Metadata(size);
    do
    {
        (void)Batch(offset);
        for (unsigned int i = 0U; i < 4U; i++)
        {
            SystemLogFile_Process(1U); Get(); Emit();
            offset += (size - offset > 512U) ? 512U : size - offset;
            if (offset == size) { break; }
        }
        assert(SystemLogFile_BatchResponseGet(s_frame, sizeof(s_frame), &s_length) == SystemLogFileResult_NotReady);
    } while (offset < size);
    Cancel();
}

static void Backpressure(void)
{
    uint8_t first[SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE];
    uint16_t length;
    uint32_t io;
    Metadata(4096U); (void)Batch(0U);
    SystemLogFile_Process(1U); Get();
    memcpy(first, s_frame, s_length); length = s_length; io = s_io_count;
    assert(SystemLogFile_BatchResponseGet(s_frame, sizeof(s_frame), &s_length) == SystemLogFileResult_NotReady);
    SystemLogFile_BatchResponseSent(0U);
    SystemLogFile_Process(1U); Get();
    assert(length == s_length && memcmp(first, s_frame, length) == 0 && io == s_io_count);
    Emit();
    SystemLogFile_Process(1U); Get(); Emit();
    Cancel();
}

static void Overlap(void)
{
    unsigned int id;
    Metadata(4096U); id = Batch(0U);
    SystemLogFile_Process(1U);
    Execute("LOGFILE META 1"); assert(strstr(s_reply, "code=BUSY"));
    Poll(id); assert(strstr(s_reply, "code=BAD_ARGUMENT"));
    Get(); Emit();
    Cancel();
}

static void Failure(const char *kind)
{
    Metadata(4096U); (void)Batch(strcmp(kind, "seek-error") == 0 ? 512U : 0U);
    if (strcmp(kind, "short-read") == 0) { s_short_read = 1U; }
    else if (strcmp(kind, "read-error") == 0) { s_read_error = 1U; }
    else if (strcmp(kind, "seek-error") == 0) { s_seek_error = 1U; }
    else if (strcmp(kind, "size-change") == 0) { s_pattern_size++; }
    else if (strcmp(kind, "lifecycle") == 0) { s_lifecycle = SYSTEM_STATE_FLIGHT; }
    else if (strcmp(kind, "idle") == 0) { s_now += 30000001ULL; }
    else { assert(0); }
    SystemLogFile_Process(1U); Get();
    assert(memcmp(s_frame, "ERR LOGFILE BATCH ", 18U) == 0);
    assert(s_frame[s_length - 2U] == '\r' && s_frame[s_length - 1U] == '\n');
    SystemLogFile_BatchResponseSent(1U);
    assert(SystemLogFile_BatchResponseGet(s_frame, sizeof(s_frame), &s_length) == SystemLogFileResult_NotReady);
    assert(s_live_handles == 0U);
}

static void Cancellation(const char *kind)
{
    Metadata(4096U); (void)Batch(0U);
    if (strcmp(kind, "cancel-io") == 0) { s_cancel_in_read = 1U; }
    SystemLogFile_Process(1U);
    if (strcmp(kind, "cancel-claimed") == 0) { Get(); }
    Execute("LOGFILE CANCEL");
    SystemLogFile_BatchResponseSent(1U);
    assert(SystemLogFile_BatchResponseGet(s_frame, sizeof(s_frame), &s_length) == SystemLogFileResult_NotReady);
    SystemLogFile_Process(1U);
    assert(s_live_handles == 0U);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    Execute("LOGFILE CAPS");
    assert(strstr(s_reply, "batch_version=1 batch_count=4"));
    if (strncmp(argv[1], "size=", 5U) == 0) { Boundary((uint32_t)strtoul(argv[1] + 5, NULL, 10)); }
    else if (strcmp(argv[1], "backpressure") == 0) { Backpressure(); }
    else if (strcmp(argv[1], "overlap") == 0) { Overlap(); }
    else if (strncmp(argv[1], "cancel-", 7U) == 0) { Cancellation(argv[1]); }
    else { Failure(argv[1]); }
    assert(s_live_handles == 0U);
    puts("PASS synthetic bounded batch");
    return 0;
}
