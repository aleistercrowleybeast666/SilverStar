/* White-box formatter boundary: coherent synthetic cached metadata, not a
 * claimed 4-GiB hash execution. Production parser, read backend and format run. */
#define main LogFileFixture_Main
#include "test_log_file_service.c"
#undef main
#include "../../plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_log_file.c"

int main(void)
{
    s_pattern_size = UINT32_MAX;
    s_worker.file_id = 999999U;
    s_worker.size = UINT32_MAX;
    s_worker.crc = UINT32_MAX;
    s_worker.cached = 1U;
    s_mailbox.sequence = UINT32_MAX - 1U;
    unsigned int id = Submit("LOGFILE READ 999999 1-FFFFFFFF-FFFFFFFF 4294967231");
    assert(id == UINT32_MAX);
    Finish(id);
    assert(strlen(s_reply) == 255U);
    assert(strstr(s_reply, "length=64 crc32=") != NULL);
    assert(strstr(s_reply, "data=BFC0C1C2C3C4C5C6") != NULL);
    assert(strcmp(s_reply + strlen(s_reply) - 16U, "F7F8F9FAFBFCFDFE") == 0);
    printf("%s\n", s_reply);
    Execute("LOGFILE META 1"); assert(strstr(s_reply, "code=NOT_READY"));
    return 0;
}
