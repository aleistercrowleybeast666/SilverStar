/* Real service+adapter; synthetic storage only. Frames are decoded again by
 * GSHC's production Python codec in the invoking pytest regression. */
#define main LegacyFixture_Main
#include "test_log_file_service.c"
#undef main

static char s_block_token[32];
static uint8_t s_frame[SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE];
static uint16_t s_frame_length;

static void Metadata(uint32_t size)
{
    unsigned int id;
    const char *token;
    s_pattern_enabled = 1U; s_pattern_size = size;
    id = Submit("LOGFILE META 1"); Finish(id);
    assert(strstr(s_reply, "OK LOGFILE META"));
    token = strstr(s_reply, "token="); assert(token);
    assert(sscanf(token, "token=%31s", s_block_token) == 1);
}

static unsigned int Block(uint32_t offset)
{
    char line[160];
    assert(snprintf(line, sizeof(line), "LOGFILE BLOCK 1 %s %lu 1122334455667788 %lu",
        s_block_token, (unsigned long)offset, (unsigned long)(offset / 512U)) > 0);
    return Submit(line);
}

static void BinaryGet(void)
{
    uint32_t before = s_io_count;
    assert(SystemLogFile_BinaryResponseGet(s_frame, sizeof(s_frame), &s_frame_length) == SystemLogFileResult_Ok);
    assert(s_frame_length >= 3U && s_frame_length <= sizeof(s_frame));
    assert(s_frame[0] == 0U && s_frame[s_frame_length - 1U] == 0U);
    assert(s_io_count == before);
    printf("FRAME_HEX ");
    for (uint16_t i = 0U; i < s_frame_length; i++) { printf("%02X", s_frame[i]); }
    puts("");
}

static void Cancel(void)
{
    Execute("LOGFILE CANCEL"); assert(strstr(s_reply, "cleanup_complete=0"));
    SystemLogFile_Process(1U); assert(s_live_handles == 0U);
}

static void Boundary(uint32_t size)
{
    uint32_t offset = 0U;
    Metadata(size);
    do
    {
        unsigned int id = Block(offset);
        uint32_t count = (size - offset > 512U) ? 512U : size - offset;
        Finish(id); assert(s_reply[0] == '\0'); BinaryGet();
        offset += count;
    } while (offset < size);
    /* Exact EOF zero-length read is legal, including for an empty source. */
    unsigned int id = Block(size); Finish(id); BinaryGet();
    Cancel();
}

static void Replay(void)
{
    uint8_t first[SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE];
    uint16_t first_length;
    uint32_t io;
    Metadata(513U);
    unsigned int id = Block(0U); Finish(id); BinaryGet();
    first_length = s_frame_length; memcpy(first, s_frame, first_length); io = s_io_count;
    Poll(id); BinaryGet();
    assert(first_length == s_frame_length && memcmp(first, s_frame, first_length) == 0);
    assert(s_io_count == io);
    id = Block(0U); Finish(id); BinaryGet(); /* New request ID, same source bytes. */
    Cancel();
}

static void Failure(const char *kind)
{
    Metadata(513U);
    unsigned int id = Block(0U); Finish(id); BinaryGet();
    if (strcmp(kind, "short-read") == 0) { s_short_read = 1U; }
    else if (strcmp(kind, "read-error") == 0) { s_read_error = 1U; }
    else if (strcmp(kind, "seek-error") == 0) { s_seek_error = 1U; }
    else if (strcmp(kind, "lifecycle") == 0) { s_lifecycle = SYSTEM_STATE_FLIGHT; }
    else if (strcmp(kind, "size-change") == 0) { s_size_change = 1U; }
    else if (strcmp(kind, "cancel-io") == 0) { s_cancel_in_read = 1U; }
    else { assert(0); }
    id = Block(0U); Finish(id);
    assert(strncmp(s_reply, "ERR LOGFILE BLOCK ", 18U) == 0);
    assert(SystemLogFile_BinaryResponseGet(s_frame, sizeof(s_frame), &s_frame_length) == SystemLogFileResult_NotReady);
    assert(s_frame_length == 0U && s_live_handles == 0U);
}

static void BadArguments(void)
{
    static const char *suffixes[] = {
        "0 0000000000000000 0", "0 112233445566778 0", "0 112233445566778Z 0",
        "0 1122334455667788 1", "514 1122334455667788 1",
        "0 1122334455667788 4294967296", "0 1122334455667788 0 extra"
    };
    Metadata(513U);
    for (unsigned int i = 0U; i < sizeof(suffixes) / sizeof(suffixes[0]); i++)
    {
        char line[160];
        assert(snprintf(line, sizeof(line), "LOGFILE BLOCK 1 %s %s", s_block_token, suffixes[i]) > 0);
        uint32_t before = s_io_count; Execute(line);
        assert(strstr(s_reply, "code=BAD_ARGUMENT")); assert(s_io_count == before);
    }
    Cancel();
}

static void InvalidatedCompletion(const char *kind)
{
    Metadata(513U);
    unsigned int id = Block(0U); Finish(id);
    if (strcmp(kind, "capacity") == 0)
    {
        assert(SystemLogFile_BinaryResponseGet(s_frame, 1U, &s_frame_length) == SystemLogFileResult_BadArgument);
        assert(s_frame_length == 0U);
        Poll(id); BinaryGet();
    }
    else
    {
        if (strcmp(kind, "idle") == 0) { s_now += 30000001ULL; }
        else
        {
            Execute("LOGFILE CANCEL");
            Poll(id); assert(strncmp(s_reply, "PENDING LOGFILE BLOCK ", 21U) == 0);
            assert(SystemLogFile_BinaryResponseGet(s_frame, sizeof(s_frame), &s_frame_length) == SystemLogFileResult_NotReady);
        }
        SystemLogFile_Process(1U); Poll(id);
        assert(strstr(s_reply, "code=TIMEOUT") || strstr(s_reply, "code=CANCELLED"));
        assert(SystemLogFile_BinaryResponseGet(s_frame, sizeof(s_frame), &s_frame_length) == SystemLogFileResult_NotReady);
        assert(s_live_handles == 0U);
    }
    Cancel();
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    Execute("LOGFILE CAPS");
    assert(strstr(s_reply, "max_chunk=64") && strstr(s_reply, "block_version=1 max_block=512 block_encoding=COBS block_window=1"));
    if (strncmp(argv[1], "size=", 5U) == 0) { Boundary((uint32_t)strtoul(argv[1] + 5, NULL, 10)); }
    else if (strcmp(argv[1], "replay") == 0) { Replay(); }
    else if (strcmp(argv[1], "arguments") == 0) { BadArguments(); }
    else if ((strcmp(argv[1], "idle") == 0) || (strcmp(argv[1], "capacity") == 0) || (strcmp(argv[1], "cancel-done") == 0))
    { InvalidatedCompletion(argv[1]); }
    else { Failure(argv[1]); }
    assert(s_live_handles == 0U);
    puts("PASS synthetic bounded block regression");
    return 0;
}
