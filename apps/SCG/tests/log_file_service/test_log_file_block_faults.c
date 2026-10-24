/* Host-only terminal assertion interception. Never linked into target firmware
 * and never evidence of MCU recovery. Production service is included intact. */
#include <setjmp.h>
#define main LegacyFixture_Main
#define SilverStarAssert_Check FixtureAssert_Check
#include "test_log_file_service.c"
#undef SilverStarAssert_Check
#undef main

static jmp_buf s_terminal;
static SilverStarAssertReasonId s_reason;
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line;
    if (condition == 0U) { s_reason = reason; longjmp(s_terminal, 1); }
}
#include "../../plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_log_file.c"

static void Guard(unsigned int fault)
{
    uint8_t output[SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE];
    uint16_t length = 0U;
    (void)memset(output, 0xA5, sizeof(output));
    s_mailbox.request.id = 1U; s_mailbox.request.operation = LOG_FILE_BLOCK;
    s_mailbox.state = LOG_FILE_DONE; s_mailbox.cancelled = 0U;
    s_binary_request = 1U; s_mailbox.block_length = 48U;
    if (fault == 0U) { s_mailbox.block_length = 1U; }
    else if (fault == 1U) { s_mailbox.block_length = LOG_FILE_BLOCK_RAW_SIZE + 1U; }
    else if (fault == 2U) { s_mailbox.block_length = 47U; }
    s_reason = 0U;
    if (setjmp(s_terminal) == 0)
    {
        if (fault <= 2U)
        { (void)SystemLogFile_BinaryResponseGet(output, sizeof(output), &length); }
        else if (fault == 3U) { (void)LogFile_BlockEncode(output, LOG_FILE_BLOCK_RAW_SIZE + 1U); }
        else
        {
            LogFileRequest request = {0};
            request.size = 1U; request.offset = 2U;
            LogFile_BlockHeaderWrite(&request, 1U);
        }
        assert(0 && "corrupt internal state did not enter terminal trap");
    }
    assert(s_reason == SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    /* The production fail-stop never returns. Only the Host interceptor
     * repairs fixture lock depth so a separate independent case can run. */
    s_critical_depth = 0U;
    for (unsigned int i = 0U; i < sizeof(output); i++) { assert(output[i] == 0xA5U); }
}

int main(void)
{
    for (unsigned int fault = 0U; fault < 5U; fault++) { Guard(fault); }
    for (unsigned int pattern = 0U; pattern < 4U; pattern++)
    {
        uint8_t guarded[SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE + 2U];
        memset(guarded, 0xA5, sizeof(guarded));
        for (unsigned int i = 0U; i < LOG_FILE_BLOCK_RAW_SIZE; i++)
        {
            uint8_t value = (pattern == 0U) ? 0U : (pattern == 1U) ? 255U :
                (pattern == 2U) ? (uint8_t)i : (uint8_t)((i * 137U + 29U) % 256U);
            guarded[5U + i] = value;
        }
        uint16_t length = LogFile_BlockEncode(&guarded[1], LOG_FILE_BLOCK_RAW_SIZE);
        assert(length <= SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE && guarded[0] == 0xA5U &&
               guarded[sizeof(guarded)-1U] == 0xA5U);
        printf("ENCODER_HEX %u ", pattern);
        for (uint16_t i = 0U; i < length; i++) { printf("%02X", guarded[1U+i]); }
        puts("");
    }
    puts("PASS 5 Host-only terminal trap cases; output unpublished");
    return 0;
}
